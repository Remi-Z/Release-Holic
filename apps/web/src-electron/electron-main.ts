import { app, BrowserWindow, shell } from 'electron';
import path from 'node:path';
let mainWindow: BrowserWindow | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({ width: 1370, height: 900, minWidth: 380, minHeight: 650, backgroundColor: '#fbfafc', title: 'Release-Holic', webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => { if (url.startsWith('https://')) void shell.openExternal(url); return { action: 'deny' }; });
  mainWindow.webContents.on('will-navigate', (event, url) => { const current = mainWindow?.webContents.getURL(); if (current && new URL(url).origin !== new URL(current).origin) { event.preventDefault(); if (url.startsWith('https://')) void shell.openExternal(url); } });
  if (process.env.APP_URL) void mainWindow.loadURL(process.env.APP_URL);
  else void mainWindow.loadFile(path.join(app.getAppPath(), 'index.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}
app.whenReady().then(createWindow).catch(() => app.quit());
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (!mainWindow) createWindow(); });
