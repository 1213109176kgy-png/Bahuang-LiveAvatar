const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('desktop',{
  services:action=>ipcRenderer.invoke('services',action),
  importModel:kind=>ipcRenderer.invoke('model-import',kind),
  logs:()=>ipcRenderer.invoke('logs'),
  openExternal:url=>ipcRenderer.invoke('open-external',url),
  onError:callback=>ipcRenderer.on('service-error',(_event,message)=>callback(message))
});
