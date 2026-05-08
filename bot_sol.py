# -*- coding: utf-8 -*-
import requests
import pandas as pd
import time
import threading
import os
from datetime import datetime
from flask import Flask, jsonify, Response, request as freq

# ── Configuracion ─────────────────────────────────────
SIMBOLO        = "SOUSDT_UMCBL"   # Bitget futuros perpetuos SOL
SIMBOLO_TICKER = "SOLUSDT"
CAPITAL        = 100.0            # Capital virtual en USDT
PUERTO         = int(os.environ.get("PORT", 8765))

# ── Grid Trading Config ───────────────────────────────
# El bot divide el rango de precio en N niveles y opera entre ellos
GRID_NIVELES   = 8      # Numero de niveles de la cuadricula
GRID_RANGO_PCT = 0.04   # Rango total del grid: 4% arriba y abajo del precio actual (8% total)
GANANCIA_GRID  = 0.008  # Ganancia por cada nivel: 0.8%
COMISION       = 0.0006 # 0.06% futuros Bitget (maker)
APALANCAMIENTO = 3      # x3 de apalancamiento (conservador para futuros)

# ── Estado ────────────────────────────────────────────
estado = {
    "precio": 0.0, "precio_max": 0.0, "precio_min": 9999999.0,
    "capital": CAPITAL, "capital_inicio": CAPITAL,
    "capital_efectivo": CAPITAL * APALANCAMIENTO,  # con apalancamiento
    "ganancia_total": 0.0, "ganancia_hoy": 0.0,
    "comisiones_total": 0.0,
    "grid_superior": 0.0, "grid_inferior": 0.0,
    "grid_niveles": [], "grid_activo": False,
    "operaciones": [], "log": [], "marcas": [],
    "rsi": 0.0, "tendencia": "NEUTRAL",
    "ops_total": 0, "ops_hoy": 0, "ops_ganadoras": 0,
    "inicio_ts": datetime.now().isoformat(),
    "inicio_ms": int(datetime.now().timestamp() * 1000),
    "motivo": "Iniciando grid...",
    "apalancamiento": APALANCAMIENTO,
    "modo": "FUTUROS GRID x" + str(APALANCAMIENTO),
}

# ── API Bitget publica ────────────────────────────────
BASE = "https://api.bitget.com"

def get_precio():
    try:
        r = requests.get(f"{BASE}/api/mix/v1/market/ticker?symbol={SIMBOLO}", timeout=5)
        d = r.json()
        return float(d["data"]["last"])
    except:
        try:
            r = requests.get(f"{BASE}/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL", timeout=5)
            return float(r.json()["data"]["close"])
        except:
            return 0.0

def get_velas_api(tf="1m", limit=200):
    try:
        tf_map = {"1m":"1m","5m":"5m","15m":"15m","1h":"1H","4h":"4H"}
        gran = tf_map.get(tf, "1m")
        r = requests.get(
            f"{BASE}/api/mix/v1/market/candles",
            params={"symbol":SIMBOLO,"granularity":gran,"limit":limit},
            timeout=8
        )
        data = r.json().get("data", [])
        return [{"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data]
    except:
        return []

def get_rsi(periodo=14):
    try:
        velas = get_velas_api("15m", 60)
        if len(velas) < periodo + 2:
            return 50.0
        closes = pd.Series([v["c"] for v in velas])
        delta  = closes.diff()
        gain   = delta.clip(lower=0).rolling(periodo).mean()
        loss   = (-delta.clip(upper=0)).rolling(periodo).mean()
        rs     = gain / loss
        rsi    = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 1)
    except:
        return 50.0

# ── Grid Trading Engine ───────────────────────────────
class GridEngine:
    def __init__(self):
        self.niveles      = []   # lista de precios del grid
        self.posiciones   = {}   # precio_nivel -> {"activa": bool, "cantidad": float, "entrada": float}
        self.precio_base  = 0.0
        self.capital_por_nivel = 0.0
        self.inicializado = False

    def inicializar(self, precio_actual):
        self.precio_base = precio_actual
        rango            = precio_actual * GRID_RANGO_PCT
        precio_inf       = precio_actual - rango
        precio_sup       = precio_actual + rango
        paso             = (precio_sup - precio_inf) / GRID_NIVELES

        self.niveles = [round(precio_inf + i * paso, 3) for i in range(GRID_NIVELES + 1)]
        self.capital_por_nivel = (estado["capital"] * APALANCAMIENTO) / GRID_NIVELES
        self.posiciones = {n: {"activa": False, "cantidad": 0.0, "entrada": 0.0} for n in self.niveles}
        self.inicializado = True

        estado["grid_inferior"] = self.niveles[0]
        estado["grid_superior"] = self.niveles[-1]
        estado["grid_niveles"]  = self.niveles
        estado["grid_activo"]   = True

        log(f"Grid inicializado | Rango: {self.niveles[0]:.2f} - {self.niveles[-1]:.2f} | {GRID_NIVELES} niveles | {self.capital_por_nivel:.2f} USDT/nivel")

    def tick(self, precio_actual):
        if not self.inicializado:
            return

        ahora = time.time()

        for i in range(len(self.niveles) - 1):
            nivel_compra = self.niveles[i]
            nivel_venta  = self.niveles[i + 1]
            pos          = self.posiciones[nivel_compra]

            # COMPRA: precio toca nivel inferior del rango
            if not pos["activa"] and precio_actual <= nivel_compra * 1.001:
                cantidad   = self.capital_por_nivel / precio_actual
                com        = self.capital_por_nivel * COMISION
                pos["activa"]   = True
                pos["cantidad"] = cantidad
                pos["entrada"]  = precio_actual
                estado["comisiones_total"] = round(estado["comisiones_total"] + com, 4)
                estado["marcas"].append({"t":int(ahora*1000),"tipo":"compra","precio":precio_actual})
                if len(estado["marcas"]) > 300: estado["marcas"].pop(0)
                log(f"GRID BUY nivel {i+1}/{GRID_NIVELES} | {precio_actual:.3f} | Cant:{cantidad:.4f} | TP:{nivel_venta:.3f}")

            # VENTA: posicion abierta y precio sube al nivel superior
            elif pos["activa"] and precio_actual >= nivel_venta * 0.999:
                ganancia_bruta = pos["cantidad"] * (nivel_venta - pos["entrada"])
                com            = pos["cantidad"] * nivel_venta * COMISION
                ganancia_neta  = ganancia_bruta - com
                estado["capital"]         += ganancia_neta
                estado["ganancia_total"]  = round(estado["ganancia_total"] + ganancia_neta, 4)
                estado["ganancia_hoy"]    = round(estado["ganancia_hoy"] + ganancia_neta, 4)
                estado["comisiones_total"] = round(estado["comisiones_total"] + com, 4)
                estado["ops_total"]       += 1
                estado["ops_hoy"]         += 1
                if ganancia_neta > 0:
                    estado["ops_ganadoras"] += 1

                estado["operaciones"].insert(0, {
                    "hora":      datetime.now().strftime("%H:%M:%S"),
                    "tipo":      "GRID SELL",
                    "nivel":     i + 1,
                    "entrada":   pos["entrada"],
                    "salida":    precio_actual,
                    "ganancia":  round(ganancia_neta, 4),
                    "comision":  round(com, 4),
                })
                if len(estado["operaciones"]) > 200: estado["operaciones"].pop()

                estado["marcas"].append({"t":int(ahora*1000),"tipo":"venta","precio":precio_actual})
                if len(estado["marcas"]) > 300: estado["marcas"].pop(0)

                pos["activa"]   = False
                pos["cantidad"] = 0.0
                pos["entrada"]  = 0.0

                log(f"GRID SELL nivel {i+1}/{GRID_NIVELES} | {pos['entrada']:.3f}->{precio_actual:.3f} | +{ganancia_neta:.4f} USDT | Total:{estado['ganancia_total']:.4f}")

        # Reinicializar grid si precio sale del rango
        if precio_actual < self.niveles[0] * 0.99 or precio_actual > self.niveles[-1] * 1.01:
            log(f"Precio fuera del grid ({precio_actual:.2f}). Reiniciando grid...")
            self.inicializar(precio_actual)

grid = GridEngine()

# ── Flask ─────────────────────────────────────────────
app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>SOL Grid Bot - Futuros</title>
<script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0f;color:#e8e8f0;font-family:monospace;padding:14px;font-size:13px}
.top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.title{font-size:17px;font-weight:bold;letter-spacing:2px}.title span{color:#7c4dff}
.subtitle{font-size:10px;color:#ff9100;margin-top:3px}
.info-row{display:flex;gap:14px;font-size:11px;color:#606080;margin-top:4px;flex-wrap:wrap}
.info-row b{color:#ffd740}
.live{display:flex;align-items:center;gap:6px;font-size:11px;color:#00e676}
.dot{width:8px;height:8px;border-radius:50%;background:#00e676;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
.cards{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin-bottom:10px}
.card{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:10px 12px}
.cl{font-size:9px;letter-spacing:2px;color:#606080;text-transform:uppercase;margin-bottom:4px}
.cv{font-size:17px;font-weight:bold;line-height:1.1}
.cs{font-size:10px;color:#606080;margin-top:3px}
.g{color:#00e676}.r{color:#ff1744}.y{color:#ffd740}.b{color:#40c4ff}.p{color:#7c4dff}.o{color:#ff9100}.m{color:#606080}
.sbar{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:9px 14px;margin-bottom:10px;display:flex;align-items:center;gap:10px}
.sdot{width:10px;height:10px;border-radius:50%}
.cw{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:12px;margin-bottom:10px}
.ch{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px}
.ctitle{font-size:10px;letter-spacing:2px;color:#606080;text-transform:uppercase}
.tfs{display:flex;gap:5px}
.tb{background:#1a1a24;border:1px solid #2a2a3a;color:#606080;padding:3px 9px;border-radius:4px;cursor:pointer;font-size:11px;font-family:monospace}
.tb:hover,.tb.active{background:#7c4dff;border-color:#7c4dff;color:#fff}
#chart{width:100%;height:280px}
.mid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.box{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:12px}
.bt{font-size:10px;letter-spacing:2px;color:#606080;text-transform:uppercase;margin-bottom:10px}
.grid-visual{display:flex;flex-direction:column;gap:3px;margin-top:6px}
.grid-level{display:flex;align-items:center;gap:8px;font-size:11px;padding:4px 8px;border-radius:4px;background:#1a1a24}
.grid-level.activo{background:rgba(0,230,118,.08);border:1px solid rgba(0,230,118,.2)}
.grid-price{width:70px;color:#606080}
.grid-bar{flex:1;height:6px;background:#2a2a3a;border-radius:3px;overflow:hidden;position:relative}
.grid-bar-fill{height:100%;border-radius:3px;background:#7c4dff;transition:width .3s}
.grid-label{font-size:10px;width:60px;text-align:right}
.ir{display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #2a2a3a}
.ir:last-child{border-bottom:none}
.il{color:#606080;width:140px;font-size:11px}
.iv{text-align:right;font-size:11px;flex:1}
.bot{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sb{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:12px;max-height:240px;overflow-y:auto}
.st{font-size:10px;letter-spacing:2px;color:#606080;text-transform:uppercase;margin-bottom:8px}
.ll{font-size:10px;padding:3px 0;border-bottom:1px solid rgba(42,42,58,.3);color:#9090b0;line-height:1.5}
.ll:last-child{border-bottom:none}
.or{display:grid;grid-template-columns:50px 80px 40px 1fr 65px 70px;gap:5px;font-size:10px;padding:4px 0;border-bottom:1px solid rgba(42,42,58,.3);align-items:center}
.or:last-child{border-bottom:none}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-track{background:#1a1a24}::-webkit-scrollbar-thumb{background:#2a2a3a;border-radius:2px}
@media(max-width:1100px){.cards{grid-template-columns:repeat(4,1fr)}.mid,.bot{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="top">
  <div>
    <div class="title">SOL/<span>USDT</span> GRID BOT
      <span style="font-size:11px;background:rgba(255,145,0,.15);color:#ff9100;border:1px solid rgba(255,145,0,.3);padding:2px 8px;border-radius:4px;margin-left:8px" id="modo-badge">FUTUROS x3</span>
      <span style="font-size:11px;color:#606080;margin-left:6px">via Bitget</span>
    </div>
    <div class="subtitle">Grid Trading | 8 niveles | ±4% rango | 0.8% ganancia/nivel</div>
    <div class="info-row">
      <div>Activo: <b id="uptime">00:00:00</b></div>
      <div>Ops hoy: <b id="ops-hoy">0</b></div>
      <div>Total ops: <b id="ops-total">0</b></div>
      <div>Ganadoras: <b id="ops-gan" class="g">0</b></div>
      <div>Max: <b id="pmax" class="g">-</b></div>
      <div>Min: <b id="pmin" class="r">-</b></div>
    </div>
  </div>
  <div class="live"><div class="dot"></div>PAPER TRADING FUTUROS</div>
</div>

<div class="cards">
  <div class="card"><div class="cl">Precio SOL</div><div class="cv b" id="precio">-</div><div class="cs">USDT ahora</div></div>
  <div class="card"><div class="cl">Capital</div><div class="cv" id="balance">-</div><div class="cs" id="bpct">-</div></div>
  <div class="card"><div class="cl">Ganancia total</div><div class="cv" id="ganancia">-</div><div class="cs" id="gpct">-</div></div>
  <div class="card"><div class="cl">Ganancia hoy</div><div class="cv" id="ganancia-hoy">-</div><div class="cs">sesion actual</div></div>
  <div class="card"><div class="cl">Comisiones</div><div class="cv o" id="com">-</div><div class="cs">pagadas</div></div>
  <div class="card"><div class="cl">Neto real</div><div class="cv" id="neto">-</div><div class="cs">ganancias - com.</div></div>
  <div class="card"><div class="cl">RSI (14)</div><div class="cv" id="rsi-c">-</div><div class="cs" id="rsi-s">-</div></div>
  <div class="card"><div class="cl">Grid activo</div><div class="cv g" id="grid-rango">-</div><div class="cs" id="grid-cs">8 niveles</div></div>
</div>

<div class="sbar">
  <div class="sdot" id="sdot" style="background:#ffd740"></div>
  <div style="flex:1;font-size:12px" id="stext">Iniciando...</div>
  <div style="font-size:10px;color:#606080" id="stime">-</div>
</div>

<div class="cw">
  <div class="ch">
    <div class="ctitle">SOL/USDT — Tiempo real &nbsp;<span style="color:#00e676;font-size:10px" id="ws-st">● conectando</span></div>
    <div class="tfs">
      <button class="tb active" onclick="ctf('1m')">1m</button>
      <button class="tb" onclick="ctf('5m')">5m</button>
      <button class="tb" onclick="ctf('15m')">15m</button>
      <button class="tb" onclick="ctf('1h')">1h</button>
      <button class="tb" onclick="ctf('4h')">4h</button>
    </div>
  </div>
  <div id="chart"></div>
</div>

<div class="mid">
  <div class="box">
    <div class="bt">Cuadricula Grid — niveles activos</div>
    <div class="grid-visual" id="grid-visual">
      <div class="m" style="font-size:11px">Cargando grid...</div>
    </div>
  </div>
  <div class="box">
    <div class="bt">Estadisticas</div>
    <div class="ir"><span class="il">Capital inicial</span><span class="iv m" id="s-ci">-</span></div>
    <div class="ir"><span class="il">Capital efectivo (x3)</span><span class="iv b" id="s-ce">-</span></div>
    <div class="ir"><span class="il">Ganancia por ciclo grid</span><span class="iv g">~0.8% / nivel</span></div>
    <div class="ir"><span class="il">Comision por op.</span><span class="iv o">0.06% (maker)</span></div>
    <div class="ir"><span class="il">Ganancia neta/ciclo</span><span class="iv g">~0.74%</span></div>
    <div class="ir"><span class="il">Comisiones totales</span><span class="iv o" id="s-com">-</span></div>
    <div class="ir"><span class="il">Win rate</span><span class="iv" id="s-wr">-</span></div>
    <div class="ir"><span class="il">Tendencia mercado</span><span class="iv" id="s-tend">-</span></div>
  </div>
</div>

<div class="bot">
  <div class="sb">
    <div class="st">Log en tiempo real</div>
    <div id="log"></div>
  </div>
  <div class="sb">
    <div class="st">Operaciones grid</div>
    <div id="ops"><div class="m">Sin operaciones todavia</div></div>
  </div>
</div>

<script>
let chart, candles, emaL, gridLineas=[];
let tf="1m", uLog=[], iTs=null, uM=0, wsV=null, inicioMs=null;

function ic(){
  const el=document.getElementById("chart");
  chart=LightweightCharts.createChart(el,{width:el.offsetWidth,height:280,layout:{background:{color:"#111118"},textColor:"#9090b0"},grid:{vertLines:{color:"#1a1a24"},horzLines:{color:"#1a1a24"}},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},timeScale:{borderColor:"#2a2a3a",timeVisible:true,secondsVisible:true},rightPriceScale:{borderColor:"#2a2a3a"}});
  candles=chart.addCandlestickSeries({upColor:"#00e676",downColor:"#ff1744",borderUpColor:"#00e676",borderDownColor:"#ff1744",wickUpColor:"#00e676",wickDownColor:"#ff1744"});
  emaL=chart.addLineSeries({color:"#40c4ff",lineWidth:1,lineStyle:2});
  window.addEventListener("resize",()=>chart.applyOptions({width:el.offsetWidth}));
}

function dibujarLineasGrid(niveles){
  gridLineas.forEach(l=>{try{chart.removePriceLine(l);}catch(e){}});
  gridLineas=[];
  if(!niveles||!niveles.length)return;
  niveles.forEach((n,i)=>{
    const l=candles.createPriceLine({price:n,color:"rgba(124,77,255,0.4)",lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:i%2===0,title:i%2===0?"G"+i:""});
    gridLineas.push(l);
  });
}

function tfSeg(t){return t==="1m"?60:t==="5m"?300:t==="15m"?900:t==="1h"?3600:14400;}

function ctf(t){
  tf=t;document.querySelectorAll(".tb").forEach(b=>b.classList.toggle("active",b.textContent===t));
  if(wsV){wsV.close();wsV=null;}cargar(t);
}

async function cargar(t){
  try{
    const v=await fetch("/velas?tf="+t).then(r=>r.json());
    if(!v||v.length<2)return;
    candles.setData(v.map(x=>({time:x.t/1000,open:x.o,high:x.h,low:x.l,close:x.c})));
    const ema=[];
    for(let i=8;i<v.length;i++){const sl=v.slice(i-8,i+1).map(x=>x.c);ema.push({time:v[i].t/1000,value:sl.reduce((a,b)=>a+b,0)/9});}
    emaL.setData(ema);
    if(inicioMs){
      const ts=tfSeg(t);
      chart.timeScale().setVisibleRange({from:Math.floor(inicioMs/1000)-(ts*10),to:Math.floor(Date.now()/1000)+(ts*5)});
    }else{chart.timeScale().fitContent();}
    redibujarMarcas();
    const wi=t==="4h"?"4h":t==="1h"?"1h":t==="15m"?"15m":t==="5m"?"5m":"1m";
    wsV=new WebSocket(`wss://stream.binance.com:9443/ws/solusdt@kline_${wi}`);
    wsV.onopen=()=>{document.getElementById("ws-st").textContent="● en vivo";document.getElementById("ws-st").style.color="#00e676";};
    wsV.onmessage=(e)=>{const k=JSON.parse(e.data).k;candles.update({time:k.t/1000,open:parseFloat(k.o),high:parseFloat(k.h),low:parseFloat(k.l),close:parseFloat(k.c)});};
    wsV.onclose=()=>{setTimeout(()=>{if(tf===t)cargar(t);},3000);};
  }catch(e){}
}

let marcasD=[];
function redibujarMarcas(){
  if(!marcasD.length)return;
  const ts=tfSeg(tf);
  candles.setMarkers(marcasD.map(x=>({time:Math.floor(x.t/1000/ts)*ts,position:x.tipo==="compra"?"belowBar":"aboveBar",color:x.tipo==="compra"?"#00e676":"#ff1744",shape:x.tipo==="compra"?"arrowUp":"arrowDown",text:x.tipo==="compra"?"BUY":"SELL"})));
}

setInterval(()=>{
  if(!iTs)return;
  const s=Math.floor((Date.now()-iTs)/1000);
  document.getElementById("uptime").textContent=String(Math.floor(s/3600)).padStart(2,"0")+":"+String(Math.floor((s%3600)/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0");
},1000);

function s(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}

async function upd(){
  try{
    const d=await fetch("/estado").then(r=>r.json());
    if(!iTs){iTs=new Date(d.inicio_ts).getTime();inicioMs=d.inicio_ms||iTs;cargar(tf);}

    const cap=d.capital,ci=d.capital_inicio,gan=d.ganancia_total,com=d.comisiones_total||0,neto=gan-com;
    const pct=((cap/ci)-1)*100;

    s("precio",d.precio.toFixed(2));
    s("pmax",d.precio_max>0?d.precio_max.toFixed(2):"-");
    s("pmin",d.precio_min<9999999?d.precio_min.toFixed(2):"-");
    s("ops-hoy",d.ops_hoy||0);s("ops-total",d.ops_total||0);s("ops-gan",d.ops_ganadoras||0);

    s("balance",cap.toFixed(2)+" USDT");document.getElementById("balance").className="cv "+(pct>=0?"g":"r");
    s("bpct",(pct>=0?"+":"")+pct.toFixed(3)+"%");
    s("ganancia",(gan>=0?"+":"")+gan.toFixed(4)+" USDT");document.getElementById("ganancia").className="cv "+(gan>=0?"g":"r");
    s("gpct",(pct>=0?"+":"")+pct.toFixed(3)+"%");
    s("ganancia-hoy",(d.ganancia_hoy>=0?"+":"")+d.ganancia_hoy.toFixed(4)+" USDT");
    document.getElementById("ganancia-hoy").className="cv "+(d.ganancia_hoy>=0?"g":"r");
    s("com","-"+com.toFixed(4)+" USDT");
    s("neto",(neto>=0?"+":"")+neto.toFixed(4)+" USDT");document.getElementById("neto").className="cv "+(neto>=0?"g":"r");

    const rsi=d.rsi;s("rsi-c",rsi.toFixed(1));document.getElementById("rsi-c").className="cv "+(rsi>70?"r":rsi<30?"g":"y");
    s("rsi-s",rsi>70?"Sobrecomprado":rsi<30?"Sobrevendido":"Neutral");

    if(d.grid_superior>0){
      s("grid-rango",d.grid_inferior.toFixed(1)+"-"+d.grid_superior.toFixed(1));
      s("grid-cs","8 niveles activos");
    }

    const dot=document.getElementById("sdot");
    dot.style.background=d.grid_activo?"#00e676":"#ffd740";
    s("stext",d.grid_activo?"Grid activo — "+d.motivo:"Iniciando — "+d.motivo);
    s("stime","Actualizado: "+new Date().toLocaleTimeString());

    s("s-ci",ci.toFixed(2)+" USDT");
    s("s-ce",(ci*d.apalancamiento).toFixed(2)+" USDT");
    s("s-com","-"+com.toFixed(4)+" USDT");
    const wr=d.ops_total>0?Math.round((d.ops_ganadoras/d.ops_total)*100):0;
    s("s-wr",wr+"%");document.getElementById("s-wr").className="iv "+(wr>=50?"g":"r");
    s("s-tend",d.tendencia);document.getElementById("s-tend").className="iv "+(d.tendencia==="ALCISTA"?"g":d.tendencia==="BAJISTA"?"r":"y");

    // Cuadricula visual
    if(d.grid_niveles&&d.grid_niveles.length){
      dibujarLineasGrid(d.grid_niveles);
      const pr=d.precio;
      const html=d.grid_niveles.slice().reverse().map((n,i)=>{
        const idx=d.grid_niveles.length-1-i;
        const activo=pr>=n*0.999&&pr<=n*1.001;
        const pct2=Math.min(100,Math.max(0,((pr-d.grid_inferior)/(d.grid_superior-d.grid_inferior))*100));
        return `<div class="grid-level${activo?" activo":""}">
          <span class="grid-price">${n.toFixed(2)}</span>
          <div class="grid-bar"><div class="grid-bar-fill" style="width:${idx/(d.grid_niveles.length-1)*100}%"></div></div>
          <span class="grid-label ${pr>=n?"g":"m"}">${pr>=n?"↑ sobre":"↓ bajo"}</span>
        </div>`;
      }).join("");
      document.getElementById("grid-visual").innerHTML=html;
    }

    if(d.marcas&&d.marcas.length!==uM){uM=d.marcas.length;marcasD=d.marcas;redibujarMarcas();}

    if(JSON.stringify(d.log)!==JSON.stringify(uLog)){
      uLog=d.log;
      document.getElementById("log").innerHTML=d.log.map(l=>`<div class="ll">${l}</div>`).join("")||"<div class='m'>-</div>";
    }

    const ops=d.operaciones||[];
    if(ops.length>0){
      document.getElementById("ops").innerHTML=ops.map(o=>
        `<div class="or">
          <span class="m">${o.hora}</span>
          <span class="g">${o.tipo}</span>
          <span class="p">N${o.nivel}</span>
          <span class="m">${o.entrada.toFixed(2)}->${o.salida.toFixed(2)}</span>
          <span class="o">-${o.comision.toFixed(4)}</span>
          <span class="${o.ganancia>=0?'g':'r'}">${o.ganancia>=0?'+':''}${o.ganancia.toFixed(4)}</span>
        </div>`
      ).join("");
    }
  }catch(e){s("stext","Error de conexion");document.getElementById("sdot").style.background="#ff1744";}
}
ic();upd();setInterval(upd,2000);
</script>
</body>
</html>"""

@app.route("/")
def index(): return Response(HTML, mimetype="text/html")

@app.route("/estado")
def get_estado(): return jsonify(estado)

@app.route("/velas")
def get_velas():
    tf = freq.args.get("tf","1m")
    return jsonify(get_velas_api(tf, 300))

def log(msg):
    hora  = datetime.now().strftime("%H:%M:%S")
    linea = f"[{hora}] {msg}"
    print(linea)
    estado["log"].insert(0, linea)
    if len(estado["log"]) > 200: estado["log"].pop()

def run_bot():
    global grid
    log("Grid Bot SOL/USDT | Futuros x3 | Bitget | http://localhost:" + str(PUERTO))
    ultimo_dia  = datetime.now().date()
    inicializado = False

    while True:
        try:
            hoy = datetime.now().date()
            if hoy != ultimo_dia:
                estado["ganancia_hoy"] = 0.0
                estado["ops_hoy"]      = 0
                ultimo_dia = hoy

            precio = get_precio()
            if precio <= 0:
                time.sleep(5)
                continue

            estado["precio"]     = precio
            estado["precio_max"] = max(estado["precio_max"], precio)
            estado["precio_min"] = min(estado["precio_min"], precio)
            estado["rsi"]        = get_rsi()

            # Tendencia simple
            if estado["rsi"] > 60:   estado["tendencia"] = "ALCISTA"
            elif estado["rsi"] < 40: estado["tendencia"] = "BAJISTA"
            else:                     estado["tendencia"] = "NEUTRAL"

            # Inicializar grid la primera vez
            if not inicializado:
                grid.inicializar(precio)
                inicializado = True
                estado["motivo"] = f"Grid iniciado en {precio:.2f}"

            # Ejecutar logica del grid
            grid.tick(precio)
            estado["motivo"] = f"Precio: {precio:.2f} | Grid: {grid.niveles[0]:.2f}-{grid.niveles[-1]:.2f}"

        except Exception as e:
            log(f"ERROR: {e}")

        time.sleep(3)  # Revisa cada 3 segundos

threading.Thread(target=run_bot, daemon=True).start()

if os.environ.get("PORT") is None:
    import webbrowser
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{PUERTO}")
    print(f"Dashboard: http://127.0.0.1:{PUERTO}")

app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False)
