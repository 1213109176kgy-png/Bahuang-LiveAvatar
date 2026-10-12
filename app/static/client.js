const $ = id => document.getElementById(id);
let peer=null, sessionId='', socket=null, recording=false, micStream=null, audioContext=null, processor=null;
let samples=[], preRoll=[], voiced=false, silence=0, busy=false, releaseTimer=null;
const video=$('avatar');
let callStarted=0,dialing=false;
function updateCall(state){
  if(!$('callState'))return;
  if(dialing)return;
  $('callState').textContent=state==='connected'?'视频通话中':state==='connecting'?'正在接通…':state==='disconnected'?'连接暂时中断':'视频通话 · 等待接通';
  if(state==='connected'&&!callStarted)callStarted=Date.now();
  if(state==='ended'){callStarted=0;$('callTime').textContent='00:00';}
  const active=state!=='ended';const button=$('callHangup');button.disabled=false;button.classList.toggle('call-idle',!active);button.classList.remove('dialing');button.setAttribute('aria-label',active?'挂断通话':'视频通话');button.title=active?'挂断通话':'视频通话';button.parentElement.querySelector('span').textContent=active?'挂断':'视频通话';button.querySelector('path').setAttribute('d',active?'M4 15v-4c4-5 12-5 16 0v4l-5-2v-3M9 10v3l-5 2':'M3 6h12v12H3zM15 10l6-3v10l-6-3');
}
async function startVideoCall(){
  if(dialing)return;
  dialing=true;callStarted=0;$('callTime').textContent='00:00';const button=$('callHangup');button.disabled=true;button.classList.add('dialing');button.parentElement.querySelector('span').textContent='正在拨打';$('callState').textContent='正在拨打视频电话…';phase('正在拨打，接通后开始收音');
  try{
    await Promise.all([connect(),recording?Promise.resolve():toggleMicrophone(),new Promise(resolve=>setTimeout(resolve,3000))]);
    const deadline=Date.now()+30000;
    while(peer&&['new','connecting'].includes(peer.connectionState)&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,100));
    if(!peer||peer.connectionState!=='connected')throw new Error('视频连接未成功，请重试');
    if(!recording)throw new Error('麦克风未开启，请允许麦克风权限后重试');
    dialing=false;updateCall('connected');phase('视频通话已接通，正在听你说话');
  }catch(error){dialing=false;if(recording)await toggleMicrophone();disconnect();bubble('error',error.message);phase('通话未接通，请重试');}
}
setInterval(()=>{if(!callStarted||!$('callTime'))return;const seconds=Math.floor((Date.now()-callStarted)/1000);$('callTime').textContent=[Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].slice(seconds>=3600?0:1).map(n=>String(n).padStart(2,'0')).join(':');},1000);
if($('callFullscreen')){
  const fullscreen=$('callFullscreen'),stage=$('callStage');
  fullscreen.onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await stage.requestFullscreen();}catch{window.toast?.('无法开启全屏，请在浏览器中使用此功能。');}};
  document.addEventListener('fullscreenchange',()=>{const active=document.fullscreenElement===stage;fullscreen.setAttribute('aria-label',active?'退出全屏':'全屏');fullscreen.title=active?'退出全屏':'全屏';fullscreen.querySelector('path').setAttribute('d',active?'M3 8h5V3m8 0v5h5M8 21v-5H3m18 0h-5v5':'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5');});
  $('callHangup').onclick=async()=>{if(!peer)return startVideoCall();if(recording)await toggleMicrophone();await interrupt().catch(()=>{});disconnect();socket?.close();if(document.fullscreenElement===stage)await document.exitFullscreen();phase('通话已挂断');};
  updateCall('ended');
}
function phase(text){$('phase').textContent=text;}
function bubble(role,text){document.querySelector('.chat-empty')?.remove();const el=document.createElement('div');el.className='bubble '+role;el.textContent=(role==='user'?'你：':role==='assistant'?(window.appConfig?.role_name||'小雅')+'：':'')+text;$('history').append(el);$('history').scrollTop=$('history').scrollHeight;}
function openSocket(){
  if(socket && socket.readyState===WebSocket.OPEN)return Promise.resolve();
  return new Promise((resolve,reject)=>{
    socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/chat');
    socket.onopen=()=>{socket.send(JSON.stringify({type:'session',sessionid:sessionId}));resolve();};
    socket.onerror=()=>reject(new Error('对话服务连接失败'));
    socket.onclose=()=>{busy=false;phase('对话连接已断开，发送消息可重新连接');};
    socket.onmessage=event=>{
      const message=JSON.parse(event.data);
      if(message.type==='phase')phase(message.text);
      if(message.type==='user'||message.type==='assistant')bubble(message.type,message.text);
      if(message.type==='error'){bubble('error',message.text);busy=false;phase('本轮失败，请查看提示');}
      if(message.type==='audio'){new Audio('data:audio/wav;base64,'+message.audio).play().catch(()=>{});}
      if(message.type==='done'){
        clearTimeout(releaseTimer);
        if(message.empty){busy=false;phase('未识别到有效语音');return;}
        phase('正在播放回答');
        $('timing').textContent=`首段音频送达 ${message.first_audio_seconds} 秒；全部生成 ${message.latency} 秒，音频时长 ${message.audio_seconds} 秒。`;
        releaseTimer=setTimeout(()=>{busy=false;phase(recording?'正在听你说话':'可以继续提问');},((message.playback_seconds??message.audio_seconds)+1.2)*1000);
      }
    };
  });
}
async function connect(){
  $('connect').disabled=true;
  updateCall('connecting');
  try{
    const status=await (await fetch('/api/status')).json();
    if(!status.services.avatar)throw new Error('数字人服务尚未启动');
    peer=new RTCPeerConnection({iceServers:[]});
    peer.addTransceiver('video',{direction:'recvonly'});peer.addTransceiver('audio',{direction:'recvonly'});
    const remote=new MediaStream();video.srcObject=remote;
    peer.ontrack=event=>{remote.addTrack(event.track);video.play().catch(()=>{});};
    peer.onconnectionstatechange=()=>{if(!peer)return;const state=peer.connectionState;$('videoStatus').textContent='画面连接：'+state;updateCall(state);if(state==='failed')disconnect();};
    await peer.setLocalDescription(await peer.createOffer());
    await new Promise(resolve=>{if(peer.iceGatheringState==='complete')return resolve();const timer=setTimeout(resolve,7000);peer.addEventListener('icegatheringstatechange',()=>{if(peer.iceGatheringState==='complete'){clearTimeout(timer);resolve();}});});
    const response=await fetch('/api/avatar/offer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sdp:peer.localDescription.sdp,type:peer.localDescription.type})});
    if(!response.ok)throw new Error('数字人连接失败：'+await response.text());
    const answer=await response.json();sessionId=String(answer.sessionid);
    await peer.setRemoteDescription({sdp:answer.sdp,type:answer.type});
    await openSocket();socket.send(JSON.stringify({type:'session',sessionid:sessionId}));
    $('disconnect').disabled=false;phase('数字人已连接，可以发送文字');
  }catch(error){bubble('error',error.message);disconnect();}
}
function disconnect(){updateCall("ended");if(peer)peer.close();peer=null;video.srcObject=null;sessionId='';if(socket?.readyState===1)socket.send(JSON.stringify({type:'session',sessionid:''}));$('connect').disabled=false;$('disconnect').disabled=true;$('videoStatus').textContent='已断开';$('avatarPreview').style.visibility='visible';$('previewLabel').textContent='底片预览 · 连接后播放实时画面';}
async function submit(payload){
  if(busy){phase('请等回答结束，或先点打断');return;}
  try{await openSocket();busy=true;socket.send(JSON.stringify({type:'chat',...payload}));phase('正在处理');}
  catch(error){busy=false;bubble('error',error.message);}
}
async function interrupt(){
  clearTimeout(releaseTimer);busy=false;resetSpeech();
  if(socket?.readyState===1)socket.send(JSON.stringify({type:'interrupt'}));
  if(sessionId)await fetch('/api/avatar/interrupt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionid:sessionId})});
  phase('已打断；当前推理会结束后丢弃音频');
}
function resetSpeech(){samples=[];preRoll=[];voiced=false;silence=0;}
function wavBase64(chunks){
  const length=chunks.reduce((n,chunk)=>n+chunk.length,0),array=new ArrayBuffer(44+length*2),view=new DataView(array);
  const text=(offset,s)=>{for(let i=0;i<s.length;i++)view.setUint8(offset+i,s.charCodeAt(i));};
  text(0,'RIFF');view.setUint32(4,36+length*2,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,length*2,true);
  let pos=44;for(const chunk of chunks)for(const v of chunk){view.setInt16(pos,Math.max(-1,Math.min(1,v))*32767,true);pos+=2;}
  const bytes=new Uint8Array(array);let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);
}
async function toggleMicrophone(){
  if(recording){recording=false;processor.disconnect();micStream.getTracks().forEach(t=>t.stop());await audioContext.close();resetSpeech();$('microphone').textContent='开启麦克风';$('microphone').classList.remove('active');phase('麦克风已关闭');return;}
  try{
    await openSocket();
    micStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,...(window.appConfig?.microphone_device?{deviceId:{exact:window.appConfig.microphone_device}}:{})},video:false});
    audioContext=new AudioContext({sampleRate:16000});await audioContext.resume();
    const source=audioContext.createMediaStreamSource(micStream);processor=audioContext.createScriptProcessor(2048,1,1);
    processor.onaudioprocess=event=>{
      if(!recording||busy||dialing){resetSpeech();return;}
      const input=event.inputBuffer.getChannelData(0),ratio=audioContext.sampleRate/16000;
      const chunk=new Float32Array(Math.round(input.length/ratio));for(let i=0;i<chunk.length;i++)chunk[i]=input[Math.min(input.length-1,Math.floor(i*ratio))];
      let sum=0;for(const v of chunk)sum+=v*v;const rms=Math.sqrt(sum/chunk.length);$('level').style.width=Math.min(100,rms*1000)+'%';
      const elapsed=chunk.length/16000;
      if(rms>(window.appConfig?.vad_threshold??0.015)){if(!voiced){samples=[...preRoll];voiced=true;}silence=0;samples.push(chunk);}
      else if(voiced){samples.push(chunk);silence+=elapsed;}
      else{preRoll.push(chunk);if(preRoll.length>3)preRoll.shift();}
      const total=samples.reduce((n,c)=>n+c.length,0)/16000;
      if(voiced&&((silence>=(window.appConfig?.vad_silence??0.8)&&total>=0.5)||total>=20)){const audio=wavBase64(samples);resetSpeech();submit({audio});}
    };
    source.connect(processor);processor.connect(audioContext.destination);recording=true;
    $('microphone').textContent='关闭麦克风';$('microphone').classList.add('active');phase('正在听你说话');
  }catch(error){bubble('error','麦克风未开启：'+error.message);}
}
$('connect').onclick=connect;$('disconnect').onclick=disconnect;$('interrupt').onclick=interrupt;$('microphone').onclick=toggleMicrophone;
$('send').onclick=()=>{const text=$('text').value.trim();if(text&&!busy){submit({text});$('text').value='';}};
$('text').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('send').click();}};
$('clear').onclick=()=>{$('history').replaceChildren();if(socket?.readyState===1)socket.send(JSON.stringify({type:'clear'}));};
async function refresh(){try{const status=await(await fetch('/api/status')).json();$('states').replaceChildren();for(const[name,ok]of[['对话模型',status.services.llm],['数字人画面',status.services.avatar],['语音服务',status.ready]]){const tag=document.createElement('span');tag.className='state '+(ok?'good':'bad');tag.textContent=name+'：'+(ok?'就绪':'加载中');$('states').append(tag);}if(status.voice){const v=status.voice;const tag=document.createElement('span');tag.className='state good';tag.textContent=v.provider!=='local'?'当前声音：在线服务':v.mode==='clone'?'当前声音：录音克隆 · '+(v.engine==='official'?'官方原生':'加速流式'):'当前声音：预设音色 · '+v.speaker;tag.title=v.reference||v.model;$('states').append(tag);}if(status.error)phase(status.error);}catch{$('states').textContent='本地服务已停止';}}
refresh();setInterval(refresh,7000);
let previousFrames=0,previousTime=0;setInterval(async()=>{if(!peer||peer.connectionState!=='connected')return;const stats=await peer.getStats();stats.forEach(report=>{if(report.type==='inbound-rtp'&&report.kind==='video'){const frames=report.framesDecoded||0,time=report.timestamp;const fps=previousTime?(frames-previousFrames)*1000/(time-previousTime):0;previousFrames=frames;previousTime=time;$('videoStatus').textContent=`画面已连接 · 解码 ${fps.toFixed(1)} 帧/秒 · 累计 ${frames} 帧`;}});},2000);
let connectedAvatar='';
video.addEventListener('loadeddata',()=>{connectedAvatar=window.appConfig.avatar_id;$('previewLabel').textContent='实时画面 · 动态底片';$('avatarPreview').style.visibility='hidden';if(video.setSinkId)video.setSinkId(window.appConfig.speaker_device||'').catch(()=>window.toast?.('播放设备不可用，继续使用默认设备。'));});
window.addEventListener('settings-saved',()=>{if(peer&&connectedAvatar&&connectedAvatar!==window.appConfig.avatar_id){disconnect();setTimeout(connect,800);}if(video.setSinkId)video.setSinkId(window.appConfig.speaker_device||'').catch(()=>{});});
window.addEventListener('settings-loaded',()=>refresh());
window.addEventListener('services-stopped',async()=>{
  dialing=false;
  if(recording)await toggleMicrophone();
  disconnect();
  socket?.close();
  phase('本地服务已停止');
});
