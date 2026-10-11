const { app, BrowserWindow, ipcMain, session, dialog, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const ROOT = fs.existsSync(path.join(path.dirname(process.execPath), 'app/server.py')) ? path.dirname(process.execPath) : path.resolve(__dirname, '..');
const children = new Map();
let win, shuttingDown = false, starting = false;
const readConfig = () => JSON.parse(fs.readFileSync(path.join(ROOT, 'config/local.json'), 'utf8').replace(/^\uFEFF/, ''));
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const portUrl = () => `http://127.0.0.1:${readConfig().web_port || 7860}`;
async function available(url) { try { return (await fetch(url, { signal: AbortSignal.timeout(1500) })).ok; } catch { return false; } }
function startChild(name, executable, args, cwd, env) {
  const log = fs.openSync(path.join(ROOT, 'logs', `windows-${name}.log`), 'a');
  const child = spawn(executable, args, { cwd, windowsHide: true, env: { ...process.env, ...env }, stdio: ['ignore', log, log] });
  fs.closeSync(log);
  children.set(name, child);
  child.on('error', error => { children.delete(name); win?.webContents.send('service-error', `${name} 启动失败：${error.message}`); });
  child.on('exit', code => { if(children.get(name) === child) children.delete(name); if(code && !shuttingDown) win?.webContents.send('service-error', `${name} 已退出，错误码 ${code}。请查看运行日志。`); });
}
async function startServices() {
  if(starting) return { ok: false, message: '正在启动，请稍等' };
  starting = true;
  try {
    const c = readConfig();
      if((c.avatar_engine || 'wav2lip') === 'wav2lip' && !fs.existsSync(path.join(ROOT,'sources/LiveTalking/models/wav2lip.pth'))) {
        const choice=await dialog.showMessageBox(win,{type:'info',title:'首次运行：导入口型模型',message:'公开整合包未附带 Wav2Lip256 权重',detail:'请从 LiveTalking 官方项目获取 wav2lip256.pth，并遵守权重许可。选择文件后会复制到整合包模型目录；以后无需重复导入。',buttons:['选择模型文件','打开官方说明','取消'],defaultId:0,cancelId:2});
        if(choice.response===1){await shell.openExternal('https://github.com/lipku/LiveTalking#2-快速开始');return {ok:false,message:'获取模型后，请重新打开工作台并选择 wav2lip256.pth。'};}
        if(choice.response!==0)return {ok:false,message:'尚未导入口型模型，请准备 wav2lip256.pth 后重新打开工作台。'};
        const file=await dialog.showOpenDialog(win,{title:'选择 wav2lip256.pth',properties:['openFile'],filters:[{name:'Wav2Lip256 权重',extensions:['pth']}]});
        if(file.canceled)return {ok:false,message:'模型导入已取消。'};
        const target=path.join(ROOT,'sources/LiveTalking/models/wav2lip.pth');fs.mkdirSync(path.dirname(target),{recursive:true});await fs.promises.copyFile(file.filePaths[0],target);
      }
    if(await available(portUrl() + '/api/status')) {
      const status = await (await fetch(portUrl() + '/api/status')).json();
      if(status.runtime !== 'Windows 原生') throw new Error('当前端口上运行的是旧 WSL 服务，请先双击停止.cmd，再重新打开工作台');
      await win.loadURL(portUrl());
      return {ok:true, reused:true};
    }
    fs.mkdirSync(path.join(ROOT, 'logs'), {recursive:true});
    const py = path.join(ROOT, 'runtime/windows-python/python.exe');
    if(!fs.existsSync(py)) throw new Error('便携 Python 缺失，请使用完整整合包');
    const env = { PYTHONUTF8:'1', PYTHONUNBUFFERED:'1', HF_HUB_OFFLINE:'1', TRANSFORMERS_OFFLINE:'1', OMP_NUM_THREADS:'4', OPENBLAS_NUM_THREADS:'4', HF_HOME:path.join(ROOT,'models/huggingface'), LIVEGIRL_LLM_URL:`http://127.0.0.1:${c.llm_port}/v1` };
    if((c.llm_provider || 'local') === 'local') {
      if(await available(`http://127.0.0.1:${c.llm_port}/health`)) throw new Error('对话模型端口已被占用，请停止旧服务');
      startChild('llama', path.join(ROOT,'runtime/llama/llama-server.exe'), ['-m',path.resolve(ROOT,c.llm_model_path || 'models/Qwen3-4B-Q4_K_M.gguf'),'--alias',c.llm_model,'--host','127.0.0.1','--port',String(c.llm_port),'-c',String(c.llm_context || 2048),'--parallel','1','-ngl',String(c.llm_gpu_layers ?? 99),'-b','256','-ub','128','-t','6','-fa','on','--reasoning','off','--jinja'],ROOT,env);
    }
    if(await available(`http://127.0.0.1:${c.avatar_port}/index.html`)) throw new Error('数字人端口已被占用，请停止旧服务');
    const avatarConfig = {model:c.avatar_engine || 'wav2lip',avatar_id:c.avatar_id,batch_size:c.avatar_batch_size || 4,tts:'edgetts',REF_FILE:'zh-CN-XiaoxiaoNeural',transport:'webrtc',stun:'',max_session:1,listenport:c.avatar_port};
    const yaml = path.join(ROOT,'config/windows-livetalking.yaml');
    fs.writeFileSync(yaml,JSON.stringify(avatarConfig,null,2));
    startChild('avatar',py,['-X','utf8',path.join(ROOT,'app/avatar_server.py'),'--config',yaml],path.join(ROOT,'sources/LiveTalking'),env);
    startChild('voice',py,['-X','utf8','-m','uvicorn','app.server:app','--host','127.0.0.1','--port',String(c.web_port),'--ws-max-size','16777216'],ROOT,env);
    for(let i=0;i<90;i++) {
      if(await available(portUrl() + '/')) { await win.loadURL(portUrl()); return {ok:true}; }
      if(!children.has('voice')) throw new Error('对话服务启动失败，请检查 windows-voice.log');
      await wait(1000);
    }
    throw new Error('页面启动超时，请查看日志');
  } catch(error) { await stopServices(); return {ok:false,message:error.message}; }
  finally { starting=false; }
}
async function stopServices() {
  shuttingDown=true;
  const owned = Array.from(children.values());
  await Promise.allSettled(owned.map(child => new Promise(resolve => {
    if(!child.pid) return resolve();
    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {windowsHide:true,stdio:'ignore'});
    killer.on('error',()=>{child.kill();resolve();});
    killer.on('exit',resolve);
  })));
  children.clear();
  shuttingDown=false;
  return {ok:true};
}
function trusted(event) {
  if(event.sender !== win.webContents) throw new Error('无效调用来源');
  const url=event.senderFrame?.url || '';
  if(!url.startsWith(portUrl() + '/') && !url.startsWith('file:')) throw new Error('无效页面来源');
}
app.name='数字人工作台 · 源码预览版';
app.setPath('userData',path.join(ROOT,'runtime/desktop-profile'));
if(!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.focus();}});
  app.whenReady().then(async()=>{
    const initial=readConfig();if(initial.default_avatar_id&&initial.avatar_id!==initial.default_avatar_id){initial.avatar_id=initial.default_avatar_id;fs.writeFileSync(path.join(ROOT,'config/local.json'),JSON.stringify(initial,null,2));}
    session.defaultSession.setPermissionRequestHandler((contents,permission,callback)=>callback(contents.getURL().startsWith(portUrl()+'/') && permission==='media'));
    session.defaultSession.setPermissionCheckHandler((contents,permission,origin)=>permission==='media' && origin===portUrl());
    win=new BrowserWindow({width:1440,height:960,minWidth:1100,minHeight:750,title:'数字人工作台 · 源码预览版',backgroundColor:'#f5f5f1',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.js'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
    win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    win.webContents.on('will-navigate',(event,url)=>{if(!url.startsWith(portUrl()+'/') && !url.startsWith('file:'))event.preventDefault();});
    ipcMain.handle('services',async(event,action)=>{trusted(event);if(action==='start')return startServices();if(action==='stop')return stopServices();if(action==='restart'){await stopServices();await wait(1000);return startServices();}return {ok:false,message:'无效操作'};});
    ipcMain.handle('model-import',async(event,kind)=>{
      trusted(event);
      if(!['llm','asr','tts'].includes(kind))throw new Error('无效模型类型');
      const result=await dialog.showOpenDialog(win,{title:kind==='llm'?'选择 GGUF 模型':'选择完整模型文件夹',properties:[kind==='llm'?'openFile':'openDirectory'],filters:kind==='llm'?[{name:'GGUF 模型',extensions:['gguf']}]:[]});
      if(result.canceled)return null;
      const source=result.filePaths[0], basename=path.basename(source);
      const destination=path.join(ROOT,'models',basename);
      if(kind==='llm' && path.extname(source).toLowerCase()!=='.gguf')throw new Error('请选择 GGUF 文件');
      if(kind!=='llm' && !fs.existsSync(path.join(source,'config.json')))throw new Error('所选文件夹缺少 config.json');
      if(path.resolve(source)!==path.resolve(destination)) {
        if(fs.existsSync(destination))throw new Error('同名模型已经存在，请选择已有模型或先重命名');
        await fs.promises.cp(source,destination,{recursive:true,filter:file=>!file.endsWith('.parts')});
      }
      return {path:`models/${basename}`};
    });
    ipcMain.handle('logs',event=>{trusted(event);const names=['windows-voice.log','windows-avatar.log','windows-llama.log'];return names.map(name=>({name,text:fs.existsSync(path.join(ROOT,'logs',name))?fs.readFileSync(path.join(ROOT,'logs',name),'utf8').slice(-16000):'暂无日志'}));});
    ipcMain.handle('open-external',async(event,url)=>{trusted(event);const target=new URL(url);if(target.protocol!=='https:' || target.username || target.password || !['huggingface.co','www.runninghub.cn'].includes(target.hostname))throw new Error('不支持的外部链接');await shell.openExternal(target.href);return {ok:true};});
    await win.loadFile(path.join(__dirname,'loading.html'));
    const started=await startServices();if(!started.ok)win.webContents.send('service-error',started.message);
  });
  app.on('window-all-closed',()=>{stopServices().finally(()=>app.quit());});
  app.on('before-quit',()=>{for(const child of children.values())child.kill();});
}
