window.desktop.onError(message=>{document.getElementById('state').textContent=message;});
document.getElementById('retry').onclick=async()=>{document.getElementById('state').textContent='正在启动…';const result=await window.desktop.services('start');if(!result.ok)document.getElementById('state').textContent=result.message;};
document.getElementById('logs').onclick=async()=>{document.getElementById('detail').textContent=(await window.desktop.logs()).map(x=>x.name+'\n'+x.text).join('\n\n');};
