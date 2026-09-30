// DeskPilot FreeCAD Bridge Client
// Usage: node freecad_client.js <command> [json_args]
// Examples:
//   node freecad_client.js status
//   node freecad_client.js run_python '{"code":"import FreeCAD; print(FreeCAD.Version())"}'
//   node freecad_client.js screenshot

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8765;
const cmd = process.argv[2];
const argsJson = process.argv[3] ? JSON.parse(process.argv[3]) : {};

const body = JSON.stringify({ cmd, ...argsJson });

const req = http.request({
  hostname: '127.0.0.1',
  port: PORT,
  path: '/command',
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
  timeout: 120000 // 2 min timeout for long operations
}, (res) => {
  let data = '';
  res.on('data', chunk => data += chunk);
  res.on('end', () => {
    try {
      const parsed = JSON.parse(data);
      if (parsed.ok === false) {
        console.error('ERROR:', parsed.error);
        if (parsed.traceback) console.error(parsed.traceback);
        process.exit(1);
      }
      // Handle screenshot: save to file
      if (cmd === 'screenshot' && parsed.result && parsed.result.image_base64) {
        const outPath = path.join(__dirname, `freecad_screenshot_${Date.now()}.png`);
        fs.writeFileSync(outPath, Buffer.from(parsed.result.image_base64, 'base64'));
        console.log('Screenshot saved to:', outPath);
      } else {
        console.log(JSON.stringify(parsed.result, null, 2));
      }
    } catch (e) {
      console.error('Parse error:', e.message, '\nRaw:', data.slice(0, 500));
      process.exit(1);
    }
  });
});

req.on('error', (e) => {
  console.error('Connection failed:', e.message);
  console.error('Is the DeskPilot Bridge running in FreeCAD?');
  process.exit(1);
});

req.write(body);
req.end();
