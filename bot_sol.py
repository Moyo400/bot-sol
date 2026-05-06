# -*- coding: utf-8 -*-
import ccxt
import pandas as pd
import ta
import time
import threading
import os
from datetime import datetime
from flask import Flask, jsonify, Response, request as freq

# ── Configuracion ─────────────────────────────────────
SIMBOLO        = "SOL/USDT"
CAPITAL_INICIO = 100.0
INTERVALO_SEG  = 5
PUERTO         = int(os.environ.get("PORT", 8765))
COMISION       = 0.001   # 0.1% Bitget spot
SL_PCT         = 0.006   # Stop Loss 0.6%
TP_PCT         = 0.012   # Take Profit 1.2%
COOLDOWN_SEG   = 30

# ── Modo: "spot" o "futuros" ──────────────────────────
# Para futuros cambia a "futuros" y añade tus API keys de Bitget
MODO = "spot"

# ── Estado ────────────────────────────────────────────
estado = {
    "precio": 0.0, "precio_max": 0.0, "precio_min": 9999999.0,
    "capital": CAPITAL_INICIO, "capital_inicio": CAPITAL_INICIO,
    "en_posicion": False, "precio_entrada": 0.0,
    "stop_loss": 0.0, "take_profit": 0.0,
    "cantidad_sol": 0.0, "pct_posicion": 0.0, "valor_posicion": 0.0,
    "rsi": 0.0, "rsi_prev": 0.0, "macd_his": 0.0, "ema9": 0.0,
    "tendencia": "NEUTRAL", "motivo": "Iniciando...",
    "operaciones": [], "log": [], "marcas": [],
    "comisiones_total": 0.0,
    "inicio_ts": datetime.now().isoformat(),
    "inicio_ms": int(datetime.now().timestamp() * 1000),
    "ops_hoy": 0, "ops_total": 0,
    "modo": MODO,
    "exchange": "Bitget",
}

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>SOL Bot - Bitget</title>
<script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0f;color:#e8e8f0;font-family:monospace;padding:14px;font-size:13px}
.top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.title{font-size:17px;font-weight:bold;letter-spacing:2px}.title span{color:#7c4dff}
.subtitle{font-size:10px;color:#ff9100;margin-top:3px}
.info-row{display:flex;gap:14px;font-size:11px;color:#606080;margin-top:4px;flex-wrap:wrap}
.info-row span{color:#ffd740;font-weight:bold}
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
#chart{width:100%;height:300px}
.mid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.box{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:12px}
.bt{font-size:10px;letter-spacing:2px;color:#606080;text-transform:uppercase;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}
.badge{font-size:10px;padding:2px 10px;border-radius:20px;font-weight:bold}
.bon{background:rgba(0,230,118,.12);color:#00e676;border:1px solid rgba(0,230,118,.3)}
.boff{background:rgba(96,96,128,.12);color:#606080;border:1px solid #2a2a3a}
.pg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px}
.pl{font-size:9px;color:#606080;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px}
.pv{font-size:14px;font-weight:bold}
.pb{height:5px;background:#1a1a24;border-radius:3px;overflow:hidden;margin:6px 0 3px}
.pf{height:100%;border-radius:3px;transition:width .3s}
.plb{display:flex;justify-content:space-between;font-size:10px}
.ir{display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #2a2a3a}
.ir:last-child{border-bottom:none}
.il{color:#606080;width:130px;font-size:11px}
.ib{flex:1;height:4px;background:#1a1a24;border-radius:2px;overflow:hidden;margin:0 8px}
.if{height:100%;border-radius:2px;transition:width .3s}
.iv{width:90px;text-align:right;font-size:11px}
.bot{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sb{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:12px;max-height:220px;overflow-y:auto}
.st{font-size:10px;letter-spacing:2px;color:#606080;text-transform:uppercase;margin-bottom:8px}
.ll{font-size:10px;padding:3px 0;border-bottom:1px solid rgba(42,42,58,.3);color:#9090b0;line-height:1.5}
.ll:last-child{border-bottom:none}
.or{display:grid;grid-template-columns:50px 95px 1fr 65px 75px;gap:5px;font-size:10px;padding:4px 0;border-bottom:1px solid rgba(42,42,58,.3);align-items:center}
.or:last-child{border-bottom:none}
.modo-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:bold;margin-left:8px}
.modo-spot{background:rgba(64,196,255,.15);color:#40c4ff;border:1px solid rgba(64,196,255,.3)}
.modo-futuros{background:rgba(255,145,0,.15);color:#ff9100;border:1px solid rgba(255,145,0,.3)}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-track{background:#1a1a24}::-webkit-scrollbar-thumb{background:#2a2a3a;border-radius:2px}
@media(max-width:1100px){.cards{grid-template-columns:repeat(4,1fr)}.mid,.bot{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="top">
  <div>
    <div class="title">SOL/<span>USDT</span> BOT
      <span class="modo-badge" id="modo-badge">SPOT</span>
      <span style="font-size:11px;color:#606080;margin-left:8px">via Bitget</span>
    </div>
    <div class="subtitle">Scalping RSI | SL: -0.6% | TP: +1.2% | Tiempo real</div>
    <div class="info-row">
      <div>Activo: <span id="uptime">00:00:00</span></div>
      <div>Ops hoy: <span id="ops-hoy">0</span></div>
      <div>Total: <span id="ops-total">0</span></div>
      <div>Max: <span id="pmax" class="g">-</span></div>
      <div>Min: <span id="pmin" class="r">-</span></div>
    </div>
  </div>
  <div class="live"><div class="dot"></div>PAPER TRADING</div>
</div>

<div class="cards">
  <div class="card"><div class="cl">Precio SOL</div><div class="cv b" id="precio">-</div><div class="cs">USDT ahora</div></div>
  <div class="card"><div class="cl">Balance</div><div class="cv" id="balance">-</div><div class="cs" id="bpct">-</div></div>
  <div class="card"><div class="cl">Benef. bruto</div><div class="cv" id="benef">-</div><div class="cs" id="bpct2">-</div></div>
  <div class="card"><div class="cl">Comisiones</div><div class="cv o" id="com">-</div><div class="cs">pagadas</div></div>
  <div class="card"><div class="cl">Benef. neto</div><div class="cv" id="neto">-</div><div class="cs">sin com.</div></div>
  <div class="card"><div class="cl">Tendencia</div><div class="cv" id="tend">-</div><div class="cs">EMA 9/21/50</div></div>
  <div class="card"><div class="cl">RSI (7)</div><div class="cv" id="rsi-c">-</div><div class="cs" id="rsi-s">-</div></div>
  <div class="card"><div class="cl">Operaciones</div><div class="cv p" id="nops">0</div><div class="cs" id="ratio">- / -</div></div>
</div>

<div class="sbar">
  <div class="sdot" id="sdot" style="background:#ffd740"></div>
  <div style="flex:1;font-size:12px" id="stext">Conectando...</div>
  <div style="font-size:10px;color:#606080" id="stime">-</div>
</div>

<div class="cw">
  <div class="ch">
    <div class="ctitle">SOL/USDT — Tiempo real &nbsp;<span style="color:#00e676;font-size:10px" id="ws-status">● conectando</span></div>
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
    <div class="bt"><span>Posicion actual</span><span class="badge boff" id="pbadge">ESPERANDO</span></div>
    <div class="pg">
      <div><div class="pl">Entrada</div><div class="pv m" id="pe">-</div></div>
      <div><div class="pl">Valor ahora</div><div class="pv" id="pv2">-</div></div>
      <div><div class="pl">P&amp;G</div><div class="pv" id="ppct">-</div></div>
      <div><div class="pl">SOL comprados</div><div class="pv m" id="pcant">-</div></div>
      <div><div class="pl">Stop Loss</div><div class="pv r" id="psl">-</div></div>
      <div><div class="pl">Take Profit</div><div class="pv g" id="ptp">-</div></div>
    </div>
    <div id="pw" style="display:none">
      <div style="font-size:10px;color:#606080">SL → precio → TP</div>
      <div class="pb"><div class="pf" id="pfill"></div></div>
      <div class="plb"><span class="r" id="psl2">SL</span><span class="b" id="pp2">-</span><span class="g" id="ptp2">TP</span></div>
    </div>
  </div>
  <div class="box">
    <div class="bt">Indicadores</div>
    <div class="ir"><span class="il">RSI rapido (7)</span><div class="ib"><div class="if" id="rb"></div></div><span class="iv" id="rv">-</span></div>
    <div class="ir"><span class="il">MACD Delta</span><div class="ib"><div class="if" id="mb"></div></div><span class="iv" id="mv">-</span></div>
    <div class="ir"><span class="il">EMA 9</span><div class="ib"></div><span class="iv m" id="ev">-</span></div>
    <div class="ir"><span class="il">Capital inicio</span><div class="ib"></div><span class="iv m" id="ci">-</span></div>
    <div class="ir"><span class="il">Comisiones pagadas</span><div class="ib"></div><span class="iv o" id="cv2">-</span></div>
    <div class="ir"><span class="il">Neto real</span><div class="ib"></div><span class="iv" id="nv">-</span></div>
  </div>
</div>

<div class="bot">
  <div class="sb">
    <div class="st">Log en tiempo real</div>
    <div id="log"></div>
  </div>
  <div class="sb">
    <div class="st">Operaciones</div>
    <div id="ops"><div class="m">Sin operaciones todavia</div></div>
  </div>
</div>

<script>
let chart, candles, emaL;
let tf="1m", uLog=[], iTs=null, uM=0, wsVela=null, inicioMs=null;

function ic(){
  const el=document.getElementById("chart");
  chart=LightweightCharts.createChart(el,{
    width:el.offsetWidth,height:300,
    layout:{background:{color:"#111118"},textColor:"#9090b0"},
    grid:{vertLines:{color:"#1a1a24"},horzLines:{color:"#1a1a24"}},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
    timeScale:{borderColor:"#2a2a3a",timeVisible:true,secondsVisible:true},
    rightPriceScale:{borderColor:"#2a2a3a"},
  });
  candles=chart.addCandlestickSeries({upColor:"#00e676",downColor:"#ff1744",borderUpColor:"#00e676",borderDownColor:"#ff1744",wickUpColor:"#00e676",wickDownColor:"#ff1744"});
  emaL=chart.addLineSeries({color:"#40c4ff",lineWidth:1,lineStyle:2});
  window.addEventListener("resize",()=>chart.applyOptions({width:el.offsetWidth}));
}

function tfSeg(t){return t==="1m"?60:t==="5m"?300:t==="15m"?900:t==="1h"?3600:14400;}

function ctf(t){
  tf=t;
  document.querySelectorAll(".tb").forEach(b=>b.classList.toggle("active",b.textContent===t));
  if(wsVela){wsVela.close();wsVela=null;}
  cargar(t);
}

async function cargar(t){
  try{
    const v=await fetch("/velas?tf="+t).then(r=>r.json());
    if(!v||v.length<2)return;
    const velas=v.map(x=>({time:x.t/1000,open:x.o,high:x.h,low:x.l,close:x.c}));
    candles.setData(velas);
    const ema=[];
    for(let i=8;i<velas.length;i++){
      const sl=velas.slice(i-8,i+1).map(x=>x.close);
      ema.push({time:velas[i].time,value:sl.reduce((a,b)=>a+b,0)/9});
    }
    emaL.setData(ema);
    // Centrar desde inicio del bot
    if(inicioMs){
      const ts=tfSeg(t);
      chart.timeScale().setVisibleRange({
        from:Math.floor(inicioMs/1000)-(ts*10),
        to:Math.floor(Date.now()/1000)+(ts*5)
      });
    } else {
      chart.timeScale().fitContent();
    }
    redibujarMarcas();
    // WebSocket Bitget para tiempo real
    const wi=t==="4h"?"4H":t==="1h"?"1H":t==="15m"?"15m":t==="5m"?"5m":"1m";
    // Usamos Binance WS para el grafico (solo datos publicos de precios, no trading)
    const sim="solusdt";
    wsVela=new WebSocket(`wss://stream.binance.com:9443/ws/${sim}@kline_${wi}`);
    wsVela.onopen=()=>{
      document.getElementById("ws-status").textContent="● en vivo";
      document.getElementById("ws-status").style.color="#00e676";
    };
    wsVela.onmessage=(evt)=>{
      const k=JSON.parse(evt.data).k;
      candles.update({time:k.t/1000,open:parseFloat(k.o),high:parseFloat(k.h),low:parseFloat(k.l),close:parseFloat(k.c)});
      emaL.update({time:k.t/1000,value:parseFloat(k.c)});
    };
    wsVela.onerror=()=>{
      document.getElementById("ws-status").textContent="● sin WS (actualizando cada 2s)";
      document.getElementById("ws-status").style.color="#ffd740";
    };
    wsVela.onclose=()=>{
      setTimeout(()=>{if(tf===t)cargar(t);},3000);
    };
  }catch(e){console.log("Error cargando:",e);}
}

let marcasData=[];
function redibujarMarcas(){
  if(!marcasData.length)return;
  const ts=tfSeg(tf);
  candles.setMarkers(marcasData.map(x=>({
    time:Math.floor(x.t/1000/ts)*ts,
    position:x.tipo==="compra"?"belowBar":"aboveBar",
    color:x.tipo==="compra"?"#00e676":"#ff1744",
    shape:x.tipo==="compra"?"arrowUp":"arrowDown",
    text:x.tipo==="compra"?"BUY":"SELL",
  })));
}

setInterval(()=>{
  if(!iTs)return;
  const s=Math.floor((Date.now()-iTs)/1000);
  document.getElementById("uptime").textContent=
    String(Math.floor(s/3600)).padStart(2,"0")+":"+
    String(Math.floor((s%3600)/60)).padStart(2,"0")+":"+
    String(s%60).padStart(2,"0");
},1000);

function s(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}

async function upd(){
  try{
    const d=await fetch("/estado").then(r=>r.json());
    if(!iTs){
      iTs=new Date(d.inicio_ts).getTime();
      inicioMs=d.inicio_ms||iTs;
      cargar(tf);
    }

    // Modo badge
    const mb=document.getElementById("modo-badge");
    if(d.modo==="futuros"){mb.className="modo-badge modo-futuros";mb.textContent="FUTUROS";}
    else{mb.className="modo-badge modo-spot";mb.textContent="SPOT";}

    const pr=d.precio,cap=d.capital,ci=d.capital_inicio;
    const benef=cap-ci,pct=((cap/ci)-1)*100,com=d.comisiones_total||0,neto=benef-com;

    s("precio",pr.toFixed(2));
    s("pmax",d.precio_max>0?d.precio_max.toFixed(2):"-");
    s("pmin",d.precio_min<9999999?d.precio_min.toFixed(2):"-");
    s("ops-hoy",d.ops_hoy||0);s("ops-total",d.ops_total||0);

    s("balance",cap.toFixed(2)+" USDT");
    document.getElementById("balance").className="cv "+(pct>=0?"g":"r");
    s("bpct",(pct>=0?"+":"")+pct.toFixed(3)+"%");
    s("benef",(benef>=0?"+":"")+benef.toFixed(3)+" USDT");
    document.getElementById("benef").className="cv "+(benef>=0?"g":"r");
    s("bpct2",(pct>=0?"+":"")+pct.toFixed(3)+"%");
    s("com","-"+com.toFixed(3)+" USDT");s("cv2","-"+com.toFixed(3)+" USDT");
    s("neto",(neto>=0?"+":"")+neto.toFixed(3)+" USDT");
    document.getElementById("neto").className="cv "+(neto>=0?"g":"r");
    s("nv",(neto>=0?"+":"")+neto.toFixed(3)+" USDT");
    document.getElementById("nv").className="iv "+(neto>=0?"g":"r");

    const t=d.tendencia;s("tend",t);
    document.getElementById("tend").className="cv "+(t==="ALCISTA"?"g":t==="BAJISTA"?"r":"y");
    const rsi=d.rsi;
    s("rsi-c",rsi.toFixed(1));
    document.getElementById("rsi-c").className="cv "+(rsi>65?"r":rsi<35?"g":"y");
    s("rsi-s",rsi>65?"Sobrecomprado":rsi<35?"Sobrevendido":"Neutral");
    const ops=d.operaciones||[];
    s("nops",ops.length);
    const g=ops.filter(o=>o.resultado>0).length;
    s("ratio",g+" gan / "+(ops.length-g)+" per");

    const dot=document.getElementById("sdot");
    if(d.en_posicion){dot.style.background="#00e676";s("stext","EN POSICION - "+d.motivo);}
    else{dot.style.background="#ffd740";s("stext","Buscando entrada - "+d.motivo);}
    s("stime","Actualizado: "+new Date().toLocaleTimeString());

    if(d.en_posicion){
      document.getElementById("pbadge").className="badge bon";s("pbadge","COMPRADO");
      s("pe",d.precio_entrada.toFixed(3));s("pv2",d.valor_posicion.toFixed(2)+" USDT");
      const pp=d.pct_posicion;
      s("ppct",(pp>=0?"+":"")+pp.toFixed(3)+"%");
      document.getElementById("ppct").className="pv "+(pp>=0?"g":"r");
      s("pcant",d.cantidad_sol.toFixed(4)+" SOL");
      s("psl",d.stop_loss.toFixed(3));s("ptp",d.take_profit.toFixed(3));
      document.getElementById("pw").style.display="block";
      const rng=d.take_profit-d.stop_loss;
      const av=Math.max(2,Math.min(98,((pr-d.stop_loss)/rng)*100));
      const pf=document.getElementById("pfill");
      pf.style.width=av+"%";
      pf.style.background=av>60?"#00e676":av>30?"#ffd740":"#ff1744";
      s("psl2","SL "+d.stop_loss.toFixed(3));
      s("pp2",pr.toFixed(2));
      s("ptp2","TP "+d.take_profit.toFixed(3));
    }else{
      document.getElementById("pbadge").className="badge boff";s("pbadge","ESPERANDO");
      ["pe","pv2","pcant","psl","ptp"].forEach(id=>s(id,"-"));
      s("ppct","-");document.getElementById("ppct").className="pv m";
      document.getElementById("pw").style.display="none";
    }

    s("rv",rsi.toFixed(1));
    document.getElementById("rv").className="iv "+(rsi>65?"r":rsi<35?"g":"y");
    document.getElementById("rb").style.cssText="width:"+rsi+"%;background:"+(rsi>65?"#ff1744":rsi<35?"#00e676":"#ffd740");
    const macd=d.macd_his;
    s("mv",(macd>=0?"+":"")+macd.toFixed(4));
    document.getElementById("mv").className="iv "+(macd>=0?"g":"r");
    document.getElementById("mb").style.cssText="width:"+Math.min(100,Math.abs(macd)*600)+"%;background:"+(macd>=0?"#00e676":"#ff1744");
    s("ev",d.ema9.toFixed(2));s("ci",ci.toFixed(2)+" USDT");

    if(d.marcas&&d.marcas.length!==uM){
      uM=d.marcas.length;
      marcasData=d.marcas;
      redibujarMarcas();
    }

    if(JSON.stringify(d.log)!==JSON.stringify(uLog)){
      uLog=d.log;
      document.getElementById("log").innerHTML=
        d.log.map(l=>`<div class="ll">${l}</div>`).join("")||"<div class='m'>-</div>";
    }
    if(ops.length>0){
      document.getElementById("ops").innerHTML=ops.map(o=>
        `<div class="or">
          <span class="m">${o.hora}</span>
          <span class="${o.resultado>=0?'g':'r'}">${o.tipo}</span>
          <span class="m">${o.entrada.toFixed(3)}->${o.salida.toFixed(3)}</span>
          <span class="o">-${o.comision.toFixed(3)}</span>
          <span class="${o.resultado>=0?'g':'r'}">${o.resultado>=0?'+':''}${o.resultado.toFixed(3)}</span>
        </div>`
      ).join("");
    }
  }catch(e){
    s("stext","Error de conexion");
    document.getElementById("sdot").style.background="#ff1744";
  }
}
ic();upd();setInterval(upd,2000);
</script>
</body>
</html>"""

app = Flask(__name__)

# ── Inicializar exchange Bitget ───────────────────────
def crear_exchange():
    if MODO == "futuros":
        # Para futuros necesitas API keys de Bitget
        # Ponlas aqui o como variables de entorno en Railway
        return ccxt.bitget({
            "apiKey":    os.environ.get("BITGET_API_KEY", ""),
            "secret":    os.environ.get("BITGET_SECRET", ""),
            "password":  os.environ.get("BITGET_PASSWORD", ""),  # Bitget necesita passphrase
            "options":   {"defaultType": "swap"},  # swap = futuros perpetuos
        })
    else:
        # Spot no necesita API key para leer precios publicos
        return ccxt.bitget()

exchange = crear_exchange()
ultimo_cierre = 0

@app.route("/")
def index(): return Response(HTML, mimetype="text/html")

@app.route("/estado")
def get_estado(): return jsonify(estado)

@app.route("/velas")
def get_velas():
    tf = freq.args.get("tf","1m")
    if tf not in {"1m","3m","5m","15m","1h","4h","1d"}: tf="1m"
    try:
        # Para el grafico usamos datos publicos de Bitget
        ex = ccxt.bitget()
        v  = ex.fetch_ohlcv("SOL/USDT", tf, limit=500)
        return jsonify([{"t":x[0],"o":x[1],"h":x[2],"l":x[3],"c":x[4]} for x in v])
    except Exception as e:
        return jsonify([])

def log(msg):
    hora  = datetime.now().strftime("%H:%M:%S")
    linea = f"[{hora}] {msg}"
    print(linea)
    estado["log"].insert(0, linea)
    if len(estado["log"]) > 200: estado["log"].pop()

def get_precio():
    ticker = exchange.fetch_ticker("SOL/USDT")
    return ticker["last"]

def get_ind():
    ex = ccxt.bitget()
    v  = ex.fetch_ohlcv("SOL/USDT", "1m", limit=60)
    df = pd.DataFrame(v, columns=["timestamp","open","high","low","close","volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    dc = df.iloc[:-1].copy()
    dc["rsi"]      = ta.momentum.rsi(dc["close"], window=7)
    dc["ema9"]     = ta.trend.ema_indicator(dc["close"], window=9)
    dc["ema21"]    = ta.trend.ema_indicator(dc["close"], window=21)
    dc["ema50"]    = ta.trend.ema_indicator(dc["close"], window=50)
    macd           = ta.trend.MACD(dc["close"], window_slow=12, window_fast=6, window_sign=4)
    dc["macd"]     = macd.macd()
    dc["macd_sig"] = macd.macd_signal()
    dc["macd_his"] = macd.macd_diff()
    dc["vol_ma"]   = dc["volume"].rolling(8).mean()
    return dc

def run_bot():
    global ultimo_cierre
    log(f"Bot SOL/USDT via Bitget | Modo: {MODO} | SL:0.6% TP:1.2% | http://localhost:{PUERTO}")
    ultimo_dia = datetime.now().date()

    while True:
        try:
            hoy = datetime.now().date()
            if hoy != ultimo_dia:
                estado["ops_hoy"] = 0
                ultimo_dia = hoy

            dc = get_ind()
            c  = dc.iloc[-1]
            p  = dc.iloc[-2]

            rsi      = float(c["rsi"])
            macd_his = float(c["macd_his"])
            ema9     = float(c["ema9"])

            estado["rsi"]      = round(rsi, 1)
            estado["rsi_prev"] = round(float(p["rsi"]), 1)
            estado["macd_his"] = round(macd_his, 4)
            estado["ema9"]     = round(ema9, 2)

            if c["ema9"] > c["ema21"] > c["ema50"]:   estado["tendencia"] = "ALCISTA"
            elif c["ema9"] < c["ema21"] < c["ema50"]: estado["tendencia"] = "BAJISTA"
            else:                                       estado["tendencia"] = "NEUTRAL"

            precio = get_precio()
            estado["precio"]     = precio
            estado["precio_max"] = max(estado["precio_max"], precio)
            estado["precio_min"] = min(estado["precio_min"], precio)

            ahora = time.time()

            if estado["en_posicion"]:
                pct = ((precio / estado["precio_entrada"]) - 1) * 100
                estado["pct_posicion"]   = round(pct, 3)
                estado["valor_posicion"] = round(estado["cantidad_sol"] * precio, 3)

                salir, motivo = False, ""
                if precio >= estado["take_profit"]: salir, motivo = True, "TAKE PROFIT"
                elif precio <= estado["stop_loss"]: salir, motivo = True, "STOP LOSS"

                if salir:
                    bruto = estado["cantidad_sol"] * precio
                    com   = bruto * COMISION
                    neto  = bruto - com - estado["capital"]
                    estado["capital"]          = bruto - com
                    estado["comisiones_total"] = round(estado["comisiones_total"] + com, 4)
                    estado["ops_hoy"]         += 1
                    estado["ops_total"]       += 1
                    estado["operaciones"].insert(0, {
                        "hora":      datetime.now().strftime("%H:%M:%S"),
                        "tipo":      motivo,
                        "entrada":   estado["precio_entrada"],
                        "salida":    precio,
                        "resultado": round(neto, 3),
                        "comision":  round(com, 3),
                        "pct":       round(pct, 3),
                    })
                    if len(estado["operaciones"]) > 200: estado["operaciones"].pop()
                    estado["marcas"].append({"t":int(ahora*1000),"tipo":"venta","precio":precio})
                    if len(estado["marcas"]) > 200: estado["marcas"].pop(0)
                    estado["en_posicion"] = False
                    estado["motivo"]      = f"{motivo} ({pct:+.2f}%)"
                    ultimo_cierre         = ahora
                    log(f"{'OK' if neto>0 else 'SL'} {motivo} | {estado['precio_entrada']:.3f}->{precio:.3f} ({pct:+.2f}%) | {neto:+.3f} USDT | Cap:{estado['capital']:.2f}")

            else:
                if ahora - ultimo_cierre < COOLDOWN_SEG:
                    restante = int(COOLDOWN_SEG - (ahora - ultimo_cierre))
                    estado["motivo"] = f"Cooldown {restante}s..."
                else:
                    rsi_rebote  = float(p["rsi"]) < 40 and rsi > float(p["rsi"]) and rsi < 65
                    macd_subida = macd_his > float(p["macd_his"]) and c["macd"] > c["macd_sig"]
                    sobre_ema9  = precio > ema9

                    if (rsi_rebote or macd_subida) and sobre_ema9:
                        com_c  = estado["capital"] * COMISION
                        cap_op = estado["capital"] - com_c
                        sl     = round(precio * (1 - SL_PCT), 3)
                        tp     = round(precio * (1 + TP_PCT), 3)
                        estado["cantidad_sol"]     = cap_op / precio
                        estado["precio_entrada"]   = precio
                        estado["stop_loss"]        = sl
                        estado["take_profit"]      = tp
                        estado["en_posicion"]      = True
                        estado["pct_posicion"]     = 0.0
                        estado["comisiones_total"] = round(estado["comisiones_total"] + com_c, 4)
                        estado["marcas"].append({"t":int(ahora*1000),"tipo":"compra","precio":precio})
                        razon = "RSI rebote" if rsi_rebote else "MACD cruce"
                        estado["motivo"] = f"{razon} | TP:{tp:.3f} SL:{sl:.3f}"
                        log(f"COMPRA ({razon}) | {precio:.3f} | TP:{tp:.3f} SL:{sl:.3f} | RSI:{rsi:.1f}")
                    else:
                        motivos = []
                        if not sobre_ema9:  motivos.append("Bajo EMA9")
                        if not rsi_rebote:  motivos.append(f"RSI:{rsi:.1f}")
                        if not macd_subida: motivos.append("MACD sin cruce")
                        estado["motivo"] = " | ".join(motivos) if motivos else "Analizando..."

        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(INTERVALO_SEG)

threading.Thread(target=run_bot, daemon=True).start()

if os.environ.get("PORT") is None:
    import webbrowser
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{PUERTO}")
    print(f"Dashboard: http://127.0.0.1:{PUERTO}")

app.run(host="0.0.0.0", port=PUERTO, debug=False, use_reloader=False)
