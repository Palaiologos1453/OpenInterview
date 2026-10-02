const $ = (id) => document.getElementById(id);
let room = null;
let sessionId = null;
let muted = false;
let micTracks = [];
let utterance = null;
const status = (text) => { $("status").textContent = text; };
const message = (who, text) => {
  const p = document.createElement("p");
  p.textContent = `${who}：${text}`;
  $("conversation").appendChild(p);
};

async function request(path, payload) {
  const response = await fetch(path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload || {}) });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function disconnect() {
  const old = room;
  room = null;
  if (old) await old.disconnect();
  micTracks.forEach((track) => track.stop());
  micTracks = [];
  $("audio").replaceChildren();
  $("live-transcript").textContent = "";
  utterance = null;
  $("start").disabled = false;
  $("leave").disabled = true;
  $("mute").disabled = true;
}

$("start").onclick = async () => {
  $("start").disabled = true;
  $("report").textContent = "";
  $("conversation").replaceChildren();
  let joined = false;
  try {
    // Request permissions while the user gesture is active, before model warmup.
    micTracks = await LivekitClient.createLocalTracks({audio: {echoCancellation:true, noiseSuppression:true, autoGainControl:true}, video:false});
    status("正在准备本地语音模型，首次启动需要等待……");
    const result = await request("/join", {direction_id:$("direction").value, difficulty_id:$("difficulty").value, mode_id:$("mode").value, resume_text:$("resume").value});
    joined = true;
    sessionId = result.session_id;
    const next = new LivekitClient.Room({adaptiveStream:false, dynacast:false});
    room = next;
    next.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === "audio") {
        const audio = track.attach();
        audio.autoplay = true;
        $("audio").appendChild(audio);
      }
    });
    next.on(LivekitClient.RoomEvent.DataReceived, (data, participant, kind, topic) => {
      if (room !== next) return;
      if (topic === "openinterview.transcript") {
        const event = JSON.parse(new TextDecoder().decode(data));
        if (event.type === "speech_start") utterance = event.utterance;
        if (event.utterance !== utterance) return;
        $("live-transcript").textContent = event.text
          ? `${event.type === "partial" ? "识别中（可能修正）" : "已识别"}：${event.text}` : "正在听……";
        return;
      }
      if (topic !== "openinterview.turn") return;
      const event = JSON.parse(new TextDecoder().decode(data));
      message("我", event.answer);
      message("面试官", event.turn.next_question || "面试已结束。");
      if (event.turn.is_finished) {
        status("面试已结束，可以查看报告。");
        void next.localParticipant.setMicrophoneEnabled(false);
      }
    });
    next.on(LivekitClient.RoomEvent.Reconnecting, () => status("本地音频连接正在恢复……"));
    next.on(LivekitClient.RoomEvent.Reconnected, () => status("连接已恢复，可以继续回答。"));
    next.on(LivekitClient.RoomEvent.Disconnected, () => {
      if (room === next) { void disconnect(); status("通话已断开。"); }
    });
    await next.connect(result.url, result.token, {rtcConfig: {iceServers:[]}});
    await next.startAudio();
    for (const track of micTracks) await next.localParticipant.publishTrack(track);
    muted = false;
    $("mute").textContent = "暂停麦克风";
    $("leave").disabled = false;
    $("mute").disabled = false;
    $("get-report").disabled = false;
    message("面试官", result.question);
    status("已连接。请直接回答，停顿后会自动提交。可随时插话。");
  } catch (error) {
    await disconnect();
    if (joined) await request("/leave").catch(() => {});
    status(`启动失败：${error.message}`);
  }
};

$("leave").onclick = async () => {
  await disconnect();
  await request("/leave").catch((error) => status(error.message));
  status("通话已结束，记录保存在本机。");
};
$("mute").onclick = async () => {
  muted = !muted;
  for (const track of micTracks) {
    if (muted) await track.mute(); else await track.unmute();
  }
  $("mute").textContent = muted ? "恢复麦克风" : "暂停麦克风";
};
$("get-report").onclick = async () => {
  try {
    const response = await fetch(`/report/${encodeURIComponent(sessionId)}`);
    if (!response.ok) throw new Error(await response.text());
    $("report").textContent = await response.text();
  } catch (error) { status(error.message); }
};
fetch("/health").then((response) => {
  if (!response.ok) throw new Error("本地服务尚未就绪，请运行启动脚本。");
  status("本地服务已就绪。");
}).catch((error) => status(error.message));
