(function () {
    if (window.voiceAssistantLoaded) return;
    window.voiceAssistantLoaded = true;

    const panel = document.createElement("div");
    panel.id = "commonVoiceAssistant";
    panel.innerHTML = `
        <button id="voiceMicBtn" type="button">🎤 Voice</button>
        <button id="voiceStopBtn" type="button">⏹ Stop</button>
        <div id="voiceStatus">Click Voice to start</div>
    `;
    document.body.appendChild(panel);

    const style = document.createElement("style");
    style.textContent = `
        #voiceAssistantButton,
        #voiceFloating,
        button[aria-label*="Voice Assistant"],
        button[title*="Voice Assistant"] {
            display: none !important;
        }
        #commonVoiceAssistant {
            position: fixed;
            right: 20px;
            bottom: 20px;
            z-index: 999999;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 8px;
        }
        #commonVoiceAssistant button {
            border: 0;
            border-radius: 25px;
            padding: 12px 20px;
            color: white;
            background: #3157d5;
            font-weight: bold;
            cursor: pointer;
        }
        #commonVoiceAssistant #voiceStopBtn {
            background: #d93636;
        }
        #voiceStatus {
            background: white;
            color: #222;
            padding: 8px 12px;
            border-radius: 10px;
            font-size: 13px;
            box-shadow: 0 2px 10px #0002;
        }
    `;
    document.head.appendChild(style);

    const micBtn = document.getElementById("voiceMicBtn");
    const stopBtn = document.getElementById("voiceStopBtn");
    const status = document.getElementById("voiceStatus");

    let recorder = null;
    let stream = null;
    let chunks = [];
    let recording = false;
    let busy = false;
    let cancelled = false;
    let requestController = null;

    function stopTracks() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
    }

    function speak(text, lang) {
        return new Promise(resolve => {
            speechSynthesis.cancel();

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = lang;
            utterance.rate = 1;

            utterance.onend = resolve;
            utterance.onerror = resolve;

            speechSynthesis.speak(utterance);
        });
    }

    function detectLanguage(text) {
        return /[\u0B80-\u0BFF]/.test(text) ? "ta-IN" : "en-IN";
    }

    async function startRecording() {
        try {
            if (!navigator.mediaDevices || !window.MediaRecorder) {
                status.textContent = "Please use Chrome with microphone permission.";
                return;
            }

            stream = await navigator.mediaDevices.getUserMedia({
                audio: true
            });

            if (cancelled) {
                stopTracks();
                return;
            }

            chunks = [];

            const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : "audio/webm";

            recorder = new MediaRecorder(stream, { mimeType: mime });

            recorder.ondataavailable = event => {
                if (event.data.size > 0) chunks.push(event.data);
            };

            recorder.onstop = async () => {
                stopTracks();

                if (cancelled) return;

                const audioBlob = new Blob(chunks, { type: "audio/webm" });

                if (!audioBlob.size) {
                    busy = false;
                    status.textContent = "No audio captured. Click Voice again.";
                    return;
                }

                await processAudio(audioBlob);
            };

            recorder.start();
            recording = true;
            status.textContent = "Listening... Click Voice again when finished.";
            micBtn.textContent = "Send question";
        } catch (error) {
            stopTracks();
            status.textContent = "Please allow microphone permission.";
            console.error(error);
        }
    }

    async function processAudio(blob) {
        busy = true;
        status.textContent = "Understanding your voice...";

        try {
            const formData = new FormData();
            formData.append("audio", blob, "voice.webm");

            requestController = new AbortController();

            const transcriptionResponse = await fetch("/api/transcribe", {
                method: "POST",
                body: formData,
                signal: requestController.signal
            });

            const transcriptionData = await transcriptionResponse.json();

            if (!transcriptionResponse.ok) {
                throw new Error(transcriptionData.error || "Transcription failed");
            }

            const question = (transcriptionData.text || "").trim();

            if (!question) {
                throw new Error("No speech detected. Please try again.");
            }

            const language = detectLanguage(question);

            status.textContent = "Getting your answer...";

            const chatResponse = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: question }),
                signal: requestController.signal
            });

            const data = await chatResponse.json();

            if (!chatResponse.ok) {
                throw new Error(data.reply || "Chat request failed");
            }

            if (cancelled) return;

            const answer = data.voice_reply || data.reply || "Sorry, no answer received.";

            status.textContent = "Speaking...";
            await speak(answer, data.language || language);

            if (!cancelled) {
                status.textContent = "Click Voice to ask another question.";
            }


        } catch (error) {
            if (error.name !== "AbortError" && !cancelled) {
                console.error("Voice assistant error:", error);
                status.textContent = error.message || "Unable to get an answer.";
            }
        } finally {
            busy = false;
            requestController = null;
            micBtn.textContent = "🎤 Voice";
        }
    }

    micBtn.addEventListener("click", async () => {
        if (busy) return;

        if (recording && recorder) {
            recording = false;
            status.textContent = "Processing your question...";
            micBtn.textContent = "🎤 Voice";
            recorder.stop();
            return;
        }

        cancelled = false;
        status.textContent = "Welcome to Citizen Scheme Access";

        await speak("Welcome to Citizen Scheme Access", "en-IN");

        if (!cancelled) {
            await startRecording();
        }
    });

    stopBtn.addEventListener("click", () => {
        cancelled = true;
        recording = false;
        busy = false;

        if (requestController) {
            requestController.abort();
            requestController = null;
        }

        if (recorder && recorder.state !== "inactive") {
            recorder.stop();
        }

        stopTracks();
        speechSynthesis.cancel();

        micBtn.textContent = "🎤 Voice";
        status.textContent = "Voice assistant stopped.";
    });
})();