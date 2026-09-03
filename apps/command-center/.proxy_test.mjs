const targets = [
  "http://127.0.0.1:18000/healthz",
  "http://127.0.0.1:5173/healthz",
  "http://127.0.0.1:5173/api/v1/command-center/overview",
];
for (const url of targets) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
    console.log(url, "->", res.status);
  } catch (e) {
    console.log(url, "-> ERROR", e.cause?.code ?? e.message);
  }
}
