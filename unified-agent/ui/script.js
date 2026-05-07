document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const chatMessages = document.getElementById('chatMessages');
    const newChatBtn = document.querySelector('.new-chat-btn');
    const historyList = document.querySelector('.history-list');

    // État de l'application
    let sessions = JSON.parse(localStorage.getItem('chat_sessions')) || [];
    let currentSessionId = null;

    // Initialisation
    renderHistory();
    if (sessions.length > 0) {
        loadSession(sessions[0].id);
    } else {
        createNewChat();
    }

    // --- GESTION DES SESSIONS ---

    function createNewChat() {
        const id = Date.now().toString();
        const newSession = {
            id: id,
            title: "Nouveau Chat",
            messages: [],
            archived: false,
            timestamp: new Date().toISOString()
        };
        sessions.unshift(newSession);
        currentSessionId = id;
        saveSessions();
        renderHistory();
        renderMessages();
        userInput.focus();
    }

    function saveSessions() {
        localStorage.setItem('chat_sessions', JSON.stringify(sessions));
    }

    function renderHistory() {
        historyList.innerHTML = '';
        // Filtrer pour ne montrer que les conversations non archivées
        const activeSessions = sessions.filter(s => !s.archived);

        activeSessions.forEach(session => {
            const item = document.createElement('div');
            item.className = `history-item ${session.id === currentSessionId ? 'active' : ''}`;
            
            item.innerHTML = `
                <i class="far fa-message"></i>
                <span class="session-title">${session.title}</span>
                <button class="delete-session-btn" title="Archiver">
                    <i class="fas fa-trash-alt"></i>
                </button>
            `;

            // Cliquer sur le texte pour charger
            item.onclick = (e) => {
                if (e.target.closest('.delete-session-btn')) return;
                loadSession(session.id);
            };

            // Bouton archiver
            const deleteBtn = item.querySelector('.delete-session-btn');
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                if (confirm("Archiver cette conversation ? Elle sera masquée mais restera stockée pour la traçabilité.")) {
                    session.archived = true;
                    saveSessions();
                    if (currentSessionId === session.id) {
                        currentSessionId = null;
                        if (sessions.filter(s => !s.archived).length > 0) {
                            loadSession(sessions.filter(s => !s.archived)[0].id);
                        } else {
                            createNewChat();
                        }
                    }
                    renderHistory();
                }
            };

            historyList.appendChild(item);
        });
    }

    function loadSession(id) {
        currentSessionId = id;
        renderHistory();
        renderMessages();
    }

    function renderMessages() {
        const session = sessions.find(s => s.id === currentSessionId);
        chatMessages.innerHTML = '';

        if (session.messages.length === 0) {
            // Afficher le message de bienvenue si vide
            chatMessages.innerHTML = `
                <div class="message ai-message welcome">
                    <div class="message-content">
                        <h1>Bonjour, comment puis-je vous aider aujourd'hui ?</h1>
                        <p>Je suis votre assistant intelligent Chronotime. Je peux répondre à vos questions sur les paramétrages ou les habilitations.</p>
                        <div class="suggestions">
                            <div class="suggestion-card" data-q="Explique-moi les habilitations">
                                <i class="fas fa-shield-halved"></i>
                                <span>Explique-moi les habilitations</span>
                            </div>
                            <div class="suggestion-card" data-q="Comment créer un profil ?">
                                <i class="fas fa-user-plus"></i>
                                <span>Comment créer un profil ?</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            // Ré-attacher les clics sur suggestions
            attachSuggestionEvents();
            return;
        }

        session.messages.forEach(msg => {
            displayMessage(msg.text, msg.sender, false);
        });
        chatMessages.scrollTop = chatMessages.scrollHeight;
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
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = text; // Permettre le HTML (sources)
        
        msgDiv.appendChild(contentDiv);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
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
        recognition.interimResults = false;

        recognition.onstart = () => {
            isRecording = true;
            micBtn.classList.add('recording');
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            userInput.value = transcript;
            micBtn.classList.remove('recording');
            isRecording = false;
            sendMessage(); // Envoyer automatiquement après la voix
        };

        recognition.onerror = (event) => {
            console.error("Erreur de reconnaissance vocale:", event.error);
            micBtn.classList.remove('recording');
            isRecording = false;
        };

        recognition.onend = () => {
            micBtn.classList.remove('recording');
            isRecording = false;
        };
    }

    micBtn.onclick = () => {
        if (!recognition) {
            alert("La reconnaissance vocale n'est pas supportée par votre navigateur.");
            return;
        }
        if (isRecording) {
            recognition.stop();
        } else {
            recognition.start();
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

    async function getAIResponse(query) {
        console.log("Envoi de la question au serveur:", query);
        
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message ai-message loading';
        loadingDiv.innerHTML = '<div class="message-content"><i class="fas fa-circle-notch fa-spin"></i> L\'agent réfléchit...</div>';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const response = await fetch('http://localhost:5000/api/ask', {
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
            let htmlResponse = rawText.replace(/\n/g, '<br>');
            
            if (data.sources && data.sources.length > 0) {
                htmlResponse += `
                    <div class="sources-container">
                        <p class="sources-title"><i class="fas fa-book-open"></i> Sources :</p>
                        <div class="sources-grid">
                            ${data.sources.map(s => `<div class="source-tag" title="${s.source} (${s.location})"><i class="far fa-file-alt"></i> ${s.source}</div>`).join('')}
                        </div>
                    </div>
                `;
            }

            if (session) {
                session.messages.push({ text: htmlResponse, sender: 'ai' });
                saveSessions();
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

    // --- EVENTS ---

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    newChatBtn.addEventListener('click', createNewChat);

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

    if (userProfile) {
        userProfile.onclick = (e) => {
            e.stopPropagation();
            profileMenu.classList.toggle('active');
        };
    }

    document.addEventListener('click', () => {
        if (profileMenu) profileMenu.classList.remove('active');
    });

    if (clearHistoryBtn) {
        clearHistoryBtn.onclick = () => {
            if (confirm("Voulez-vous vraiment effacer tout l'historique des conversations ?")) {
                localStorage.removeItem('agent_sessions');
                location.reload();
            }
        };
    }
});
