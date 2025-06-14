document.addEventListener('DOMContentLoaded', async () => {
    // Fetch config first
    let appConfig = {
        defaultTheme: "dark",
        defaultStylePrompt: "Read aloud in a warm and friendly tone:",
        default_audio_format: "wav",
        default_temperature: 1.0,
        default_chunk_size_chars: 1500,
        default_api_timeout_seconds: 60,
        default_voice_display_name: "Fenrir",
        default_max_text_chars: 20000
    };
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            appConfig.defaultTheme = config.default_theme;
            appConfig.defaultStylePrompt = config.default_style_prompt;
            appConfig.default_audio_format = config.default_audio_format;
            appConfig.default_temperature = config.default_temperature;
            appConfig.default_chunk_size_chars = config.default_chunk_size_chars;
            appConfig.default_api_timeout_seconds = config.default_api_timeout_seconds;
            appConfig.default_voice_display_name = config.default_voice_display_name;
            appConfig.default_max_text_chars = config.default_max_text_chars;
        }
    } catch (error) {
        console.error('Error loading config:', error);
    }

    const maxCharsMain = parseInt(document.getElementById('text-input').maxLength);
    const voiceSelect = document.getElementById('voice-select');
    const textInput = document.getElementById('text-input');
    const synthesizeButton = document.getElementById('synthesize-button');
    const styleInstructionsInput = document.getElementById('style-instructions-input');
    const styleCharCount = document.getElementById('style-char-count');
    const mainTextCharCount = document.getElementById('main-text-char-count');
    const cancelButton = document.getElementById('cancel-button');
    const temperatureSlider = document.getElementById('temperature-slider');
    const temperatureValueDisplay = document.getElementById('temperature-value');
    const chunkSizeSlider = document.getElementById('chunk-size-slider');
    const chunkSizeValueDisplay = document.getElementById('chunk-size-value');
    const apiTimeoutSlider = document.getElementById('api-timeout-slider');
    const apiTimeoutValueDisplay = document.getElementById('api-timeout-value');
    const themeToggle = document.getElementById('theme-toggle');
    const audioPlayer = document.getElementById('audio-player');
    const downloadLink = document.getElementById('download-link');
    const audioOutputSection = document.getElementById('audio-output-section');
    const statusMessage = document.getElementById('status-message');

    // Initialize controls with config values
    if (appConfig.default_temperature) {
        temperatureSlider.value = appConfig.default_temperature;
        temperatureValueDisplay.textContent = parseFloat(appConfig.default_temperature).toFixed(2);
    }
    if (appConfig.default_chunk_size_chars) {
        chunkSizeSlider.value = appConfig.default_chunk_size_chars;
        chunkSizeValueDisplay.textContent = parseInt(appConfig.default_chunk_size_chars).toLocaleString();
    }
    if (appConfig.default_api_timeout_seconds) {
        apiTimeoutSlider.value = appConfig.default_api_timeout_seconds;
        apiTimeoutValueDisplay.textContent = appConfig.default_api_timeout_seconds;
    }
    if (appConfig.default_audio_format) {
        const audioFormatRadio = document.querySelector(`input[name="audio_format"][value="${appConfig.default_audio_format}"]`);
        if (audioFormatRadio) {
            audioFormatRadio.checked = true;
        }
    }
    if (appConfig.default_style_prompt) {
        styleInstructionsInput.value = appConfig.default_style_prompt;
        styleCharCount.textContent = `${appConfig.default_style_prompt.length} / ${styleInstructionsInput.maxLength}`;
    }

    let voicesData = [];
    let currentAbortController = null;
    let currentTaskId = null;
    let userInitiatedCancel = false;
    let isCancelling = false;

    function showStatus(message, type = 'info') {
        statusMessage.textContent = message;
        statusMessage.className = 'status'; 
        if (type === 'success') {
            statusMessage.classList.add('success');
        } else if (type === 'error') {
            statusMessage.classList.add('error');
        }
    }

    function resetUIState() {
        // Only re-enable synthesize button if not in cancellation state
        synthesizeButton.disabled = isCancelling || (!voicesData || voicesData.length === 0);
        cancelButton.disabled = true;
        cancelButton.textContent = 'Cancel';
        currentAbortController = null;
        currentTaskId = null;
        userInitiatedCancel = false;
        audioOutputSection.style.display = 'none';
        downloadLink.style.display = 'none';
        // isCancelling = false; // Do not reset isCancelling here
    }

    async function loadVoices() {
        showStatus('Loading voices...', 'info');
        synthesizeButton.disabled = true;
        voiceSelect.innerHTML = ''; 

        try {
            const response = await fetch('/api/voices');
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }
            const responseData = await response.json();
            voicesData = responseData.voices;
            const preferredDefaultVoiceName = responseData.default_voice || "Fenrir"; 

            if (!voicesData || voicesData.length === 0) {
                voiceSelect.innerHTML = '<option value="">No voices available</option>';
                showStatus('No voices available from the server.', 'error');
                return; // synthesizeButton remains disabled due to finally block logic
            }

            let voiceOptions = '';
            let foundPreferredDefault = false;
            voicesData.forEach(voice => {
                const optionText = `${voice.display_name} (${voice.description || 'No description'})`;
                const isPreferredDefault = voice.display_name === preferredDefaultVoiceName;
                voiceOptions += `<option value="${voice.display_name}" ${isPreferredDefault ? 'selected' : ''}>${optionText}</option>`;
                if (isPreferredDefault) foundPreferredDefault = true;
            });
            voiceSelect.innerHTML = voiceOptions;
            
            if (!foundPreferredDefault && voicesData.length > 0) {
                voiceSelect.selectedIndex = 0; 
                showStatus(`Voices loaded. Defaulting to: ${voicesData[0].display_name}.`, 'success');
            } else if (foundPreferredDefault) {
                showStatus(`Voices loaded. Using ${preferredDefaultVoiceName} as default.`, 'success');
            } else {
                showStatus('Voices loaded, but list might be empty or default not found.', 'info');
            }
        } catch (error) {
            console.error('Error loading voices:', error);
            showStatus(`Error loading voices: ${error.message}`, 'error');
            voiceSelect.innerHTML = '<option value="">Error loading voices</option>';
        } finally {
            resetUIState(); // Reset button states based on whether voices loaded
        }
    }

    synthesizeButton.addEventListener('click', async () => {
        if (isCancelling) return; // Prevent new requests while cancelling
        const text = textInput.value.trim();
        const voiceName = voiceSelect.value;
        if (!text) {
            showStatus('Please enter text to synthesize.', 'error'); return;
        }

        userInitiatedCancel = false; 
        synthesizeButton.disabled = true;
        cancelButton.disabled = false;
        cancelButton.textContent = 'Cancel';
        audioOutputSection.style.display = 'none';
        downloadLink.style.display = 'none';

        const estimatedChars = text.length;
        const estimatedChunkSize = parseInt(chunkSizeSlider.value);
        const estimatedNumChunks = Math.max(1, Math.ceil(estimatedChars / estimatedChunkSize));
        const chunkLabel = estimatedNumChunks === 1 ? 'chunk' : 'chunks';
        showStatus(`Synthesizing ${estimatedNumChunks} ${chunkLabel} with ${voiceName}. Please wait.`, 'info');

        currentAbortController = new AbortController();
        currentTaskId = crypto.randomUUID();

        try {
            const response = await fetch('/api/synthesize', {
                method: 'POST', signal: currentAbortController.signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: currentTaskId, text, voice_name: voiceName,
                    audio_format: document.querySelector('input[name="audio_format"]:checked').value,
                    temperature: parseFloat(temperatureSlider.value),
                    style_prompt: styleInstructionsInput.value.trim(),
                    chunk_size_chars: parseInt(chunkSizeSlider.value),
                    api_timeout_seconds: parseInt(apiTimeoutSlider.value)
                }),
            });

            if (currentAbortController.signal.aborted) { // Re-check after await
                throw new DOMException('Aborted by user during server response', 'AbortError');
            }
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: "Server error or invalid JSON response." }));
                throw new Error(errorData.detail || `HTTP error! Status: ${response.status}`);
            }
            console.log('Response headers:', [...response.headers.entries()]);
            const audioBlob = await response.blob();
            console.log('Blob created:', audioBlob);
            const audioUrl = URL.createObjectURL(audioBlob);
            console.log('Object URL created:', audioUrl);
            audioPlayer.src = audioUrl;
            audioPlayer.type = audioBlob.type;
            downloadLink.href = audioUrl;
            const now = new Date();
            const dateStr = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}.${String(now.getMinutes()).padStart(2, '0')}`;
            downloadLink.download = `${dateStr}.${voiceSelect.value.replace(/\s+/g, '_')}.${document.querySelector('input[name="audio_format"]:checked').value}`;
            console.log('Setting audio player src:', audioUrl);
            audioOutputSection.style.display = 'block';
            downloadLink.style.display = 'inline-block';
            console.log('Audio elements should now be visible');
            showStatus('Synthesis successful!', 'success');
            
            // Reset only necessary states after success
            currentAbortController = null;
            currentTaskId = null;
            userInitiatedCancel = false;
            isCancelling = false;
            synthesizeButton.disabled = false;
            cancelButton.disabled = true;
            cancelButton.textContent = 'Cancel';
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('Fetch aborted.');
                if (userInitiatedCancel) {
                    showStatus('Synthesis cancelled by user. Backend notified. This may take some time to fully stop.', 'info');
                } else {
                    showStatus('Synthesis aborted (e.g., navigation or network issue).', 'info');
                }
            } else {
                console.error('Error synthesizing speech:', error);
                showStatus(`Synthesis error: ${error.message}`, 'error');
            }
            resetUIState();
        }
    });

    if (cancelButton) {
        cancelButton.addEventListener('click', () => {
            if (!currentAbortController || isCancelling) {
                console.warn("Cancel clicked but no active synthesis to cancel");
                return;
            }

            userInitiatedCancel = true;
            isCancelling = true;
            currentAbortController.abort();
            cancelButton.textContent = 'Cancelling...';
            cancelButton.disabled = true;
            synthesizeButton.disabled = true;
            
            showStatus('Cancellation request sent. Waiting for current operation to complete...', 'info');
            console.log("Cancel initiated for task:", currentTaskId);

            if (currentTaskId) {
                fetch(`/api/cancel_task/${currentTaskId}`, { method: 'POST' })
                    .then(response => response.json().catch(() => ({})))
                    .then(data => {
                        console.log('Cancel acknowledged:', data);
                        isCancelling = false;
                        resetUIState();
                    })
                    .catch(err => {
                        console.error('Cancel notification failed:', err);
                        isCancelling = false;
                        resetUIState();
                    });
            } else {
                // No task ID case - still reset after short delay
                setTimeout(() => {
                    isCancelling = false;
                    resetUIState();
                }, 1000);
            }
        });
    }

    loadVoices(); // Initial call

    // Event listeners for sliders and char counts (no changes here)
    if (temperatureSlider && temperatureValueDisplay) {
        temperatureValueDisplay.textContent = parseFloat(temperatureSlider.value).toFixed(2);
        temperatureSlider.addEventListener('input', () => { temperatureValueDisplay.textContent = parseFloat(temperatureSlider.value).toFixed(2); });
    }
    if (styleInstructionsInput && styleCharCount) {
        const maxChars = styleInstructionsInput.maxLength || 200;
        function updateStyleCharCount() {
            const currentChars = styleInstructionsInput.value.length;
            styleCharCount.textContent = `${currentChars} / ${maxChars}`;
        }
        styleInstructionsInput.addEventListener('input', updateStyleCharCount);
        updateStyleCharCount(); 
    }
    if (textInput && mainTextCharCount) {
        function updateMainTextCharCount() {
            const currentChars = textInput.value.length;
            mainTextCharCount.textContent = `${currentChars} / ${maxCharsMain}`;
        }
        textInput.addEventListener('input', updateMainTextCharCount);
        updateMainTextCharCount(); 
    }
    if (chunkSizeSlider && chunkSizeValueDisplay) {
        function updateChunkSizeDisplay() { chunkSizeValueDisplay.textContent = parseInt(chunkSizeSlider.value).toLocaleString(); }
        updateChunkSizeDisplay(); 
        chunkSizeSlider.addEventListener('input', updateChunkSizeDisplay);
    }
    if (apiTimeoutSlider && apiTimeoutValueDisplay) {
        function updateApiTimeoutDisplay() { apiTimeoutValueDisplay.textContent = apiTimeoutSlider.value; }
        updateApiTimeoutDisplay(); 
        apiTimeoutSlider.addEventListener('input', updateApiTimeoutDisplay);
    }
    if (themeToggle) {
        function applyTheme(theme) {
            document.body.classList.toggle('light-theme', theme === 'light');
            themeToggle.checked = (theme === 'light');
        }
        const savedTheme = localStorage.getItem('theme') || appConfig.defaultTheme || 'dark';
        applyTheme(savedTheme);
        themeToggle.addEventListener('change', () => {
            const newTheme = themeToggle.checked ? 'light' : 'dark';
            localStorage.setItem('theme', newTheme);
            applyTheme(newTheme);
        });
    }
});
