document.addEventListener('DOMContentLoaded', () => {
    const loginOverlay = document.getElementById('loginOverlay');
    const appMain = document.getElementById('appMain');
    const loginForm = document.getElementById('loginForm');
    const userNameDisplay = document.querySelector('.user-name');
    
    function getUserSession() {
        const session = localStorage.getItem('user_session') || sessionStorage.getItem('user_session');
        return session ? JSON.parse(session) : null;
    }

    // --- CUSTOM MODAL ---
    function showConfirm(message, title = "Confirmation") {
        return new Promise((resolve) => {
            const modal = document.getElementById('customModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalMessage = document.getElementById('modalMessage');
            const modalConfirm = document.getElementById('modalConfirm');
            const modalCancel = document.getElementById('modalCancel');

            modalTitle.textContent = title;
            modalMessage.textContent = message;
            modal.classList.add('active');

            const onConfirm = () => {
                modal.classList.remove('active');
                cleanup();
                resolve(true);
            };

            const onCancel = () => {
                modal.classList.remove('active');
                cleanup();
                resolve(false);
            };

            const cleanup = () => {
                modalConfirm.removeEventListener('click', onConfirm);
                modalCancel.removeEventListener('click', onCancel);
            };

            modalConfirm.addEventListener('click', onConfirm, { once: true });
            modalCancel.addEventListener('click', onCancel, { once: true });
        });
    }

    // --- GESTION DE SESSION ---
    function updateUserInfo(userData) {
        if (!userData) return;
        userNameDisplay.textContent = userData.name;
        const userAvatar = document.getElementById('userAvatar');
        if (userAvatar && userData.name) {
            const names = userData.name.split(' ');
            const initials = names.length > 1 
                ? (names[0][0] + names[names.length - 1][0]).toUpperCase()
                : names[0].substring(0, 2).toUpperCase();
            userAvatar.textContent = initials;
        }
        
        // Admin Panel Visibility
        const adminBtn = document.getElementById('adminPanelBtn');
        if (adminBtn) {
            if (userData.email === 'admin@inetum.com') {
                adminBtn.style.display = 'block';
                adminBtn.onclick = () => window.location.href = '/admin.html';
            } else {
                adminBtn.style.display = 'none';
            }
        }
    }

    function checkSession() {
        // Pré-remplir l'email si mémorisé
        const savedEmail = localStorage.getItem('remembered_email');
        const emailInput = document.getElementById('loginEmail');
        if (savedEmail && emailInput) {
            emailInput.value = savedEmail;
            const rememberCheckbox = document.getElementById('rememberMe');
            if (rememberCheckbox) rememberCheckbox.checked = true;
        }

        const session = localStorage.getItem('user_session') || sessionStorage.getItem('user_session');
        if (session) {
            const userData = JSON.parse(session);
            updateUserInfo(userData);
            loginOverlay.style.display = 'none';
            appMain.style.display = 'flex';
            initializeChat();
        }
    }

    if (loginForm) {
        loginForm.onsubmit = async (e) => {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            const rememberMe = document.getElementById('rememberMe').checked;
            const submitBtn = loginForm.querySelector('.login-btn');

            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Authentification...';
            submitBtn.disabled = true;

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    const userData = {
                        email: email,
                        name: data.name
                    };

                    const storage = rememberMe ? localStorage : sessionStorage;
                    storage.setItem('user_session', JSON.stringify(userData));
                    
                    // Mémoriser l'email si demandé
                    if (rememberMe) {
                        localStorage.setItem('remembered_email', email);
                    } else {
                        localStorage.removeItem('remembered_email');
                    }
                    
                    // Animation de sortie
                    loginOverlay.style.opacity = '0';
                    loginOverlay.style.transition = 'opacity 0.5s ease';
                    
                    setTimeout(() => {
                        loginOverlay.style.display = 'none';
                        appMain.style.display = 'flex';
                        updateUserInfo(userData);
                        initializeChat();
                    }, 500);
                } else {
                    alert(data.message || "Email ou mot de passe incorrect");
                    submitBtn.innerHTML = 'Se connecter';
                    submitBtn.disabled = false;
                }
            } catch (error) {
                console.error("Login error:", error);
                alert("Erreur de connexion au serveur d'authentification.");
                submitBtn.innerHTML = 'Se connecter';
                submitBtn.disabled = false;
            }
        };
    }

    checkSession();

    function initializeChat() {
        loadSessions();
    }

    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const chatMessages = document.getElementById('chatMessages');
    const newChatBtn = document.querySelector('.new-chat-btn');

    // --- GESTION DES SESSIONS (Serveur + Local) ---
    let sessions = [];
    let currentSessionId = null;
    let isShowingArchives = false;

    async function loadSessions() {
        const userData = getUserSession();
        if (!userData) return;

        try {
            const response = await fetch(`/api/sessions?email=${userData.email}`);
            sessions = await response.json();
            
            if (sessions.length > 0) {
                loadSession(sessions[0].id);
            } else {
                createNewChat();
            }
        } catch (error) {
            console.error("Erreur chargement sessions:", error);
            renderHistory();
        }
    }

    async function saveCurrentSession() {
        if (!currentSessionId) return;
        const session = sessions.find(s => s.id === currentSessionId);
        if (!session) return;

        const userData = getUserSession();
        if (!userData) return;

        // Mise à jour du timestamp pour que ça apparaisse en haut dans pgAdmin
        session.timestamp = new Date().toISOString();

        try {
            await fetch('/api/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: userData.email, session: session })
            });
        } catch (error) {
            console.error("Erreur sauvegarde serveur:", error);
        }
    }

    function renderHistory() {
        const historyList = document.querySelector('.history-list');
        if (!historyList) return;
        historyList.innerHTML = '';

        const sectionTitle = document.querySelector('.section-title');
        if (sectionTitle) {
            sectionTitle.textContent = isShowingArchives ? 'CONVERSATIONS ARCHIVÉES' : 'HISTORIQUE RÉCENT';
        }

        // Filtrer les sessions selon le mode (archives ou actif)
        const filteredSessions = sessions.filter(s => isShowingArchives ? s.isArchived : !s.isArchived);

        filteredSessions.forEach(session => {
            const item = document.createElement('div');
            item.className = `history-item ${session.id === currentSessionId ? 'active' : ''} ${session.isPinned ? 'pinned' : ''}`;
            item.innerHTML = `
                <i class="far fa-comment-dots"></i>
                <span class="history-title">${session.title}</span>
                ${session.isPinned ? '<i class="fas fa-thumbtack pinned-indicator"></i>' : ''}
                <div class="history-options">
                    <i class="fas fa-ellipsis-h"></i>
                </div>
                <div class="history-dropdown" id="dropdown-${session.id}">
                    <div class="dropdown-item rename-action"><i class="fas fa-pen"></i> Renommer</div>
                    <div class="dropdown-item pin-action"><i class="fas fa-thumbtack"></i> ${session.isPinned ? 'Désépingler' : 'Épingler le chat'}</div>
                    <div class="dropdown-item archive-action"><i class="fas fa-box-archive"></i> ${session.isArchived ? 'Désarchiver' : 'Archiver'}</div>
                    <div class="dropdown-divider"></div>
                    <div class="dropdown-item delete" data-id="${session.id}"><i class="fas fa-trash-alt"></i> Supprimer</div>
                </div>
            `;
            
            item.onclick = (e) => {
                const optionsBtn = e.target.closest('.history-options');
                const deleteBtn = e.target.closest('.delete');
                const renameBtn = e.target.closest('.rename-action');
                const pinBtn = e.target.closest('.pin-action');
                const archiveBtn = e.target.closest('.archive-action');
                
                if (optionsBtn) {
                    e.stopPropagation();
                    const dropdown = item.querySelector('.history-dropdown');
                    const isActive = dropdown.classList.contains('active');
                    
                    document.querySelectorAll('.history-dropdown').forEach(d => d.classList.remove('active'));
                    
                    if (!isActive) {
                        const rect = optionsBtn.getBoundingClientRect();
                        
                        // Pré-calculer la position pour éviter le débordement vertical
                        dropdown.style.display = 'flex';
                        dropdown.style.visibility = 'hidden';
                        const dropdownHeight = dropdown.offsetHeight;
                        dropdown.style.display = '';
                        dropdown.style.visibility = '';

                        let topPos = rect.top;
                        if (topPos + dropdownHeight > window.innerHeight) {
                            topPos = window.innerHeight - dropdownHeight - 20;
                        }
                        
                        dropdown.style.top = `${topPos}px`;
                        dropdown.style.left = `${rect.right + 10}px`;
                        dropdown.classList.add('active');
                    }
                } else if (deleteBtn) {
                    e.stopPropagation();
                    deleteSession(deleteBtn.getAttribute('data-id'));
                } else if (renameBtn) {
                    e.stopPropagation();
                    renameSession(session.id);
                } else if (pinBtn) {
                    e.stopPropagation();
                    togglePinSession(session.id);
                } else if (archiveBtn) {
                    e.stopPropagation();
                    toggleArchiveSession(session.id);
                } else if (e.target.closest('.dropdown-item')) {
                    e.stopPropagation();
                    item.querySelector('.history-dropdown').classList.remove('active');
                } else {
                    loadSession(session.id);
                }
            };
            historyList.appendChild(item);
        });
    }

    async function renameSession(id) {
        const session = sessions.find(s => s.id === id);
        if (!session) return;
        
        // Fermer le dropdown
        document.querySelectorAll('.history-dropdown').forEach(d => d.classList.remove('active'));

        // Trouver l'élément DOM correspondant
        const historyItems = document.querySelectorAll('.history-item');
        let targetItem = null;
        historyItems.forEach(item => {
            const dropdown = item.querySelector('.history-dropdown');
            if (dropdown && dropdown.id === `dropdown-${id}`) {
                targetItem = item;
            }
        });

        if (!targetItem) return;

        const titleSpan = targetItem.querySelector('.history-title');
        const currentTitle = session.title;

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'history-title-input';
        input.value = currentTitle;
        
        titleSpan.replaceWith(input);
        input.focus();
        input.select();

        const finishRename = async () => {
            const newTitle = input.value.trim();
            if (newTitle && newTitle !== currentTitle) {
                session.title = newTitle;
                await saveSessionToBackend(session);
            }
            renderHistory();
        };

        input.onblur = finishRename;
        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                input.onblur = null;
                finishRename();
            } else if (e.key === 'Escape') {
                input.onblur = null;
                renderHistory();
            }
        };
    }

    async function togglePinSession(id) {
        const session = sessions.find(s => s.id === id);
        if (!session) return;
        session.isPinned = !session.isPinned;
        
        // Trier pour mettre les épinglés en haut
        sessions.sort((a, b) => {
            if (a.isPinned && !b.isPinned) return -1;
            if (!a.isPinned && b.isPinned) return 1;
            return new Date(b.timestamp) - new Date(a.timestamp);
        });
        
        renderHistory();
        saveSessionToBackend(session);
    }

    async function toggleArchiveSession(id) {
        const session = sessions.find(s => s.id === id);
        if (!session) return;
        session.isArchived = !session.isArchived;
        
        if (session.isArchived && currentSessionId === id) {
            const nextSession = sessions.find(s => !s.isArchived);
            if (nextSession) loadSession(nextSession.id);
            else createNewChat();
        }
        
        renderHistory();
        saveSessionToBackend(session);
    }


    async function saveSessionToBackend(session) {
        const userData = getUserSession();
        if (!userData) return;

        try {
            await fetch('/api/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: userData.email, session: session })
            });
        } catch (error) {
            console.error("Erreur sauvegarde serveur:", error);
        }
    }

    async function deleteSession(id) {
        const confirmed = await showConfirm("Supprimer définitivement cette conversation ?", "Supprimer le chat");
        if (!confirmed) return;

        const userData = getUserSession();
        if (!userData) return;

        try {
            await fetch(`/api/sessions/${id}?email=${userData.email}`, {
                method: 'DELETE'
            });
            sessions = sessions.filter(s => s.id !== id);
            if (currentSessionId === id) {
                if (sessions.length > 0) loadSession(sessions[0].id);
                else createNewChat();
            } else {
                renderHistory();
            }
        } catch (error) {
            console.error("Erreur suppression:", error);
        }
    }

    function createNewChat() {
        const id = 'chat_' + Date.now();
        const newSession = {
            id: id,
            title: "Nouvelle conversation",
            messages: [],
            timestamp: new Date().toISOString()
        };
        sessions.unshift(newSession);
        loadSession(id);
        saveCurrentSession();
    }

    function loadSession(id) {
        currentSessionId = id;
        const session = sessions.find(s => s.id === id);
        chatMessages.innerHTML = '';
        
        if (session && session.messages.length > 0) {
            session.messages.forEach(msg => {
                displayMessage(msg.text, msg.sender || msg.type, false);
            });
        } else {
            showWelcome();
        }
        renderHistory();
    }

    function showWelcome() {
        const userData = getUserSession();
        let firstName = "";
        if (userData && userData.name) {
            firstName = userData.name.split(' ')[0];
        }

        chatMessages.innerHTML = `
            <div class="message ai-message welcome fade-in">
                <div class="message-content">
                    <h1>Bonjour ${firstName}, comment puis-je vous aider ?</h1>
                    <p>Votre assistant intelligent Inetum est prêt. Posez vos questions.</p>
                    <div class="suggestions">
                        <div class="suggestion-card" data-q="C'est quoi une habilitation">
                            <i class="fas fa-shield-halved"></i>
                            <span>C'est quoi une habilitation</span>
                        </div>
                        <div class="suggestion-card" data-q="Procédure pour créer un profil">
                            <i class="fas fa-book"></i>
                            <span>Procédure pour créer un profil</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
        attachSuggestionEvents();
    }

    // --- MESSAGERIE ---

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        const session = sessions.find(s => s.id === currentSessionId);
        
        // Mettre à jour le titre si c'est le premier message
        if (session.messages.length === 0) {
            session.title = text.length > 25 ? text.substring(0, 25) + "..." : text;
            renderHistory();
        }

        // Ajouter message utilisateur
        const userMsg = { text, sender: 'user' };
        session.messages.push(userMsg);
        displayMessage(text, 'user');
        
        userInput.value = '';
        userInput.style.height = 'auto';
        saveSessions();

        // Réponse IA
        await getAIResponse(text);
    }

    function displayMessage(text, sender, animate = true) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}-message ${animate ? 'fade-in' : ''}`;
        
        let html = '';
        if (sender === 'ai') {
            html += `<div class="message-icon"><i class="fas fa-robot"></i></div>`;
        }

        let actionsHtml = '';
        if (sender === 'ai' && !text.includes('welcome')) {
            actionsHtml = `
                <div class="message-actions">
                    <button class="action-btn"><i class="fas fa-copy"></i> Copy Code</button>
                    <button class="action-btn"><i class="fas fa-sync"></i> Regenerate</button>
                </div>
            `;
        }

        html += `<div class="message-content">${actionsHtml}${text}</div>`;
        msgDiv.innerHTML = html;
        
        chatMessages.appendChild(msgDiv);
        
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: animate ? 'smooth' : 'auto'
        });
    }

    // --- VOIX & MULTIMODALITÉ ---
    const micBtn = document.getElementById('micBtn');
    let isRecording = false;
    let recognition = null;

    // Initialisation de la reconnaissance vocale
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.lang = 'fr-FR';
        recognition.continuous = false;
        recognition.interimResults = true; // Permettre les résultats intermédiaires pour plus de réactivité

        recognition.onstart = () => {
            isRecording = true;
            micBtn.classList.add('recording');
            userInput.placeholder = "Écoute en cours...";
            userInput.value = "";
        };

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(result => result[0])
                .map(result => result.transcript)
                .join('');
            
            userInput.value = transcript;
            
            if (event.results[0].isFinal) {
                recognition.stop();
                sendMessage(); // Envoyer automatiquement
            }
        };

        recognition.onerror = (event) => {
            console.error("Erreur de reconnaissance vocale:", event.error);
            stopRecording();
            if (event.error === 'not-allowed') {
                alert("Microphone non autorisé. Veuillez activer les permissions.");
            }
        };

        recognition.onend = () => {
            stopRecording();
        };
    }

    function stopRecording() {
        isRecording = false;
        micBtn.classList.remove('recording');
        userInput.placeholder = "Ask Unified anything...";
    }

    micBtn.onclick = () => {
        if (!recognition) {
            alert("La reconnaissance vocale n'est pas supportée par votre navigateur.");
            return;
        }
        if (isRecording) {
            recognition.stop();
        } else {
            try {
                recognition.start();
            } catch (e) {
                console.error("Recognition start error:", e);
                recognition.stop();
            }
        }
    };

    // Synthèse vocale (TTS)
    function speak(text) {
        // Nettoyer le texte du HTML pour la voix
        const cleanText = text.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ');
        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.lang = 'fr-FR';
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        
        // Sélectionner une voix féminine naturelle si disponible
        const voices = window.speechSynthesis.getVoices();
        const frenchVoice = voices.find(v => v.lang.startsWith('fr') && v.name.includes('Google')) || voices.find(v => v.lang.startsWith('fr'));
        if (frenchVoice) utterance.voice = frenchVoice;

        window.speechSynthesis.speak(utterance);
    }

    function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // Ajouter au session state
        const session = sessions.find(s => s.id === currentSessionId);
        if (session) {
            session.messages.push({ text: text, sender: 'user' });
            // Mettre à jour le titre si c'est le premier message
            if (session.messages.length === 1) {
                session.title = text.substring(0, 30) + (text.length > 30 ? '...' : '');
                renderHistory();
            }
            saveCurrentSession();
        }

        displayMessage(text, 'user');
        userInput.value = '';
        userInput.style.height = 'auto';
        
        getAIResponse(text);
    }

    async function getAIResponse(query) {
        console.log("Envoi de la question au serveur:", query);
        
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message ai-message loading';
        loadingDiv.innerHTML = '<div class="message-content"><i class="fas fa-circle-notch fa-spin"></i> L\'agent réfléchit...</div>';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const response = await fetch('/api/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: query })
            });

            if (!response.ok) {
                throw new Error(`Erreur serveur: ${response.status}`);
            }

            const data = await response.json();
            console.log("Réponse reçue du serveur:", data);
            
            chatMessages.removeChild(loadingDiv);

            const session = sessions.find(s => s.id === currentSessionId);
            
            let rawText = data.answer || "Désolé, je n'ai pas pu générer de réponse.";
            let htmlResponse = marked.parse(rawText);
            
            if (data.sources && data.sources.length > 0) {
                // Déduplication intelligente côté client
                const uniqueSources = [];
                const seenNames = new Set();
                data.sources.forEach(s => {
                    const base = s.source.split('.')[0].toLowerCase().replace(/\s\(\d+\)$/, "");
                    if (!seenNames.has(base)) {
                        uniqueSources.push(s);
                        seenNames.add(base);
                    }
                });

                htmlResponse += `
                    <div class="sources-container">
                        <p class="sources-title">Sources</p>
                        <div class="sources-grid">
                            ${uniqueSources.slice(0, 4).map(s => `
                                <div class="source-tag" title="${s.source}">
                                    <i class="fas fa-file-lines"></i> ${s.source}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            if (session) {
                session.messages.push({ text: htmlResponse, sender: 'ai' });
                saveCurrentSession();
            }
            
            displayMessage(htmlResponse, 'ai');
            
            // --- PARLER (Désactivé à la demande de l'utilisateur) ---
            // speak(rawText);

        } catch (error) {
            console.error("Erreur Fetch:", error);
            if (chatMessages.contains(loadingDiv)) {
                chatMessages.removeChild(loadingDiv);
            }
            const errorMsg = `<p style="color: #ff5252;"><i class="fas fa-exclamation-triangle"></i> Erreur de connexion au serveur API. Vérifiez que app.py est lancé.</p>`;
            displayMessage(errorMsg, 'ai');
        }
    }

    // --- UPLOAD DE FICHIERS ---
    const uploadBtn = document.getElementById('uploadBtn');
    const fileInput = document.getElementById('fileInput');

    if (uploadBtn && fileInput) {
        uploadBtn.onclick = () => fileInput.click();
        
        fileInput.onchange = async (e) => {
            const files = e.target.files;
            if (files.length === 0) return;

            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }

            displayMessage(`<i class="fas fa-spinner fa-spin"></i> Téléchargement de ${files.length} fichier(s)...`, 'user');

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    const data = await response.json();
                    displayMessage(`<i class="fas fa-check-circle" style="color: #10b981;"></i> ${data.message}`, 'ai');
                } else {
                    throw new Error("Erreur lors de l'upload");
                }
            } catch (error) {
                console.error("Upload error:", error);
                displayMessage(`<i class="fas fa-times-circle" style="color: #ec4899;"></i> Erreur lors de l'upload des fichiers.`, 'ai');
            }
            fileInput.value = ''; // Reset
        };
    }

    // --- ACTIONS DE MESSAGE ---
    chatMessages.addEventListener('click', (e) => {
        const btn = e.target.closest('.action-btn');
        if (!btn) return;

        const icon = btn.querySelector('i');
        if (icon.classList.contains('fa-copy')) {
            // Logique de copie
            const content = btn.closest('.message-content').innerText.replace('Copy CodeRegenerate', '').trim();
            navigator.clipboard.writeText(content).then(() => {
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                setTimeout(() => btn.innerHTML = originalText, 2000);
            });
        } else if (icon.classList.contains('fa-sync')) {
            // Logique de régénération
            const lastUserMsg = [...document.querySelectorAll('.user-message')].pop();
            if (lastUserMsg) {
                const text = lastUserMsg.querySelector('.message-content').innerText;
                userInput.value = text;
                sendMessage();
            }
        }
    });

    // --- EVENTS ---

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    newChatBtn.addEventListener('click', () => {
        createNewChat();
    });

    function attachSuggestionEvents() {
        document.querySelectorAll('.suggestion-card').forEach(card => {
            card.onclick = () => {
                userInput.value = card.getAttribute('data-q');
                sendMessage();
            };
        });
    }

    // Auto-resize textarea
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
    });

    // --- MENU PROFIL ---
    const userProfile = document.getElementById('userProfile');
    const profileMenu = document.getElementById('profileMenu');
    const clearHistoryBtn = document.getElementById('clearHistory');
    const viewArchivesBtn = document.getElementById('viewArchives');

    if (userProfile) {
        userProfile.onclick = (e) => {
            e.stopPropagation();
            profileMenu.classList.toggle('active');
        };
    }

    if (viewArchivesBtn) {
        viewArchivesBtn.onclick = (e) => {
            e.stopPropagation();
            isShowingArchives = !isShowingArchives;
            viewArchivesBtn.innerHTML = isShowingArchives 
                ? '<i class="fas fa-comment-dots"></i> Voir les chats actifs' 
                : '<i class="fas fa-box-archive"></i> Voir les archives';
            renderHistory();
            profileMenu.classList.remove('active');
        };
    }

    document.addEventListener('click', () => {
        if (profileMenu) profileMenu.classList.remove('active');
        document.querySelectorAll('.history-dropdown').forEach(d => d.classList.remove('active'));
    });

    if (clearHistoryBtn) {
        clearHistoryBtn.onclick = async () => {
            const confirmed = await showConfirm("Voulez-vous vraiment effacer tout l'historique des conversations ?", "Effacer l'historique");
            if (confirmed) {
                localStorage.removeItem('chat_sessions');
                location.reload();
            }
        };
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.onclick = async () => {
            const confirmed = await showConfirm("Voulez-vous vous déconnecter ?", "Déconnexion");
            if (confirmed) {
                localStorage.removeItem('user_session');
                sessionStorage.removeItem('user_session');
                location.reload();
            }
        };
    }

    // --- FAQ LOGIC ---
    const faqModal = document.getElementById('faqModal');
    const openFaqBtn = document.getElementById('openFaqBtn');
    const closeFaqBtn = document.getElementById('closeFaqBtn');

    if (faqModal && openFaqBtn && closeFaqBtn) {
        openFaqBtn.addEventListener('click', () => {
            faqModal.classList.add('active');
        });

        closeFaqBtn.addEventListener('click', () => {
            faqModal.classList.remove('active');
        });

        // Fermer au clic à l'extérieur
        faqModal.addEventListener('click', (e) => {
            if (e.target === faqModal) {
                faqModal.classList.remove('active');
            }
        });

        // Gérer le clic sur une question FAQ
        document.querySelectorAll('.faq-item').forEach(item => {
            item.addEventListener('click', () => {
                const question = item.getAttribute('data-q');
                if (question) {
                    faqModal.classList.remove('active');
                    userInput.value = question;
                    sendMessage();
                }
            });
        });
    }
});
