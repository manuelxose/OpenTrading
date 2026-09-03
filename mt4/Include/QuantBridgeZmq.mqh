//+------------------------------------------------------------------+
//|                                      QuantBridgeZmq.mqh            |
//| OpenTrading — ZeroMQ transport for QuantBridgeEA (ADR-0020)      |
//+------------------------------------------------------------------+
// Thin transport wrapper around the MQL4 ZeroMQ binding
// (dingmaotu/mql-zmq, MQL4 build 600+, x86/x64 DLLs installed in
// MQL4/Libraries). The EA logic never touches sockets directly.
//
// Sockets (mirror adapters/mt4/emulator.py):
//   command  REP   bind  → Core REQ connects
//   events   PUSH  bind  → Core PULL connects
//   quotes   PUB   bind  → Core SUB  connects (multipart [topic, payload])
//
// All three channels are private loopback by default (spec §1); when the
// Core runs on another host, point the inputs at the WireGuard interface
// (ADR-0016). Never internet-exposed (§29).
//
// To enable real sockets: install mql-zmq and define QUANT_BRIDGE_ZMQ.
// Without the binding the EA still compiles and runs (it logs traffic
// instead of sending it), which keeps the EA verifiable with MetaEditor
// before the transport dependency is present.
#ifndef QUANT_BRIDGE_ZMQ_MQH
#define QUANT_BRIDGE_ZMQ_MQH

// ── Enable the real transport (uncomment after installing mql-zmq) ──────
//#define QUANT_BRIDGE_ZMQ

#ifdef QUANT_BRIDGE_ZMQ
   #include <Zmq/Zmq.mqh>
#endif

//+------------------------------------------------------------------+
//| Transport state                                                   |
//+------------------------------------------------------------------+
bool   g_qbZmqUp = false;
bool   g_qbZmqWarned = false;

#ifdef QUANT_BRIDGE_ZMQ
Context  g_qbCtx;                       // one shared context per terminal
Socket  *g_qbRep  = NULL;               // command channel (REP)
Socket  *g_qbPush = NULL;               // events (PUSH)
Socket  *g_qbPub  = NULL;               // quotes (PUB)
#endif

//+------------------------------------------------------------------+
//| Bind the three channels. Returns true when transport is live.     |
//+------------------------------------------------------------------+
bool QbZmqInit(string commandAddr, string eventsAddr, string quotesAddr)
{
#ifdef QUANT_BRIDGE_ZMQ
   if(g_qbZmqUp)
      return true;
   g_qbRep = new Socket(g_qbCtx, ZMQ_REP);
   g_qbPush = new Socket(g_qbCtx, ZMQ_PUSH);
   g_qbPub = new Socket(g_qbCtx, ZMQ_PUB);
   if(g_qbRep == NULL || g_qbPush == NULL || g_qbPub == NULL)
   {
      QbZmqDeinit();
      return false;
   }
   if(!g_qbRep.bind(commandAddr)
   || !g_qbPush.bind(eventsAddr)
   || !g_qbPub.bind(quotesAddr))
   {
      Print("QuantBridgeEA: ZeroMQ bind failed (", commandAddr, ", ",
            eventsAddr, ", ", quotesAddr, "): ", Zmq::errorMessage());
      QbZmqDeinit();
      return false;
   }
   g_qbZmqUp = true;
   Print("QuantBridgeEA: ZeroMQ bound ", commandAddr, " | ", eventsAddr, " | ", quotesAddr);
   return true;
#else
   if(!g_qbZmqWarned)
   {
      Print("QuantBridgeEA: ZeroMQ transport disabled (QUANT_BRIDGE_ZMQ not defined). "
            "Install the mql-zmq binding and define QUANT_BRIDGE_ZMQ in QuantBridgeZmq.mqh "
            "to run the real bridge; the EA will log traffic instead.");
      g_qbZmqWarned = true;
   }
   return false;
#endif
}

//+------------------------------------------------------------------+
//| Release sockets and context.                                      |
//+------------------------------------------------------------------+
void QbZmqDeinit()
{
#ifdef QUANT_BRIDGE_ZMQ
   if(g_qbRep != NULL)  { delete g_qbRep;  g_qbRep = NULL; }
   if(g_qbPush != NULL) { delete g_qbPush; g_qbPush = NULL; }
   if(g_qbPub != NULL)  { delete g_qbPub;  g_qbPub = NULL; }
#endif
   g_qbZmqUp = false;
}

bool QbZmqActive()
{
   return g_qbZmqUp;
}

//+------------------------------------------------------------------+
//| Receive one command frame (non-blocking). "" when none arrived.   |
//+------------------------------------------------------------------+
string QbZmqRecvCommand()
{
#ifdef QUANT_BRIDGE_ZMQ
   if(!g_qbZmqUp || g_qbRep == NULL)
      return "";
   ZmqMsg msg;
   if(g_qbRep.recv(msg, true))         // nowait=true → false when empty
   {
      if(msg.size() <= 0)
         return "";
      return msg.getData();
   }
#endif
   return "";
}

//+------------------------------------------------------------------+
//| Send helpers (REP reply / PUSH event / PUB multipart quote).      |
//+------------------------------------------------------------------+
bool QbZmqSendReply(string json)
{
#ifdef QUANT_BRIDGE_ZMQ
   if(g_qbZmqUp && g_qbRep != NULL)
      return g_qbRep.send(json, true);
#endif
   Print("QuantBridgeEA (no transport) reply: ", json);
   return false;
}

bool QbZmqPushEvent(string json)
{
#ifdef QUANT_BRIDGE_ZMQ
   if(g_qbZmqUp && g_qbPush != NULL)
      return g_qbPush.send(json, true);
#endif
   Print("QuantBridgeEA (no transport) event: ", json);
   return false;
}

bool QbZmqPublishQuote(string symbol, string json)
{
#ifdef QUANT_BRIDGE_ZMQ
   if(g_qbZmqUp && g_qbPub != NULL)
   {
      if(!g_qbPub.sendMore(symbol, true))   // topic frame, more to come
         return false;
      return g_qbPub.send(json, true);      // payload frame
   }
#endif
   return false;
}

#endif // QUANT_BRIDGE_ZMQ_MQH
//+------------------------------------------------------------------+
