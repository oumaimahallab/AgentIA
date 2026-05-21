document.addEventListener('DOMContentLoaded', () => {
    // Basic Security Check
    const userStr = localStorage.getItem('user_session') || sessionStorage.getItem('user_session');
    if (!userStr) {
        window.location.href = '/';
        return;
    }
    const user = JSON.parse(userStr);
    if (user.email !== 'admin@inetum.com') {
        alert("Accès non autorisé. Redirection vers le chat.");
        window.location.href = '/';
        return;
    }

    // Navigation
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.admin-section');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Update active nav
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');

            // Show target section
            const target = item.getAttribute('data-target');
            sections.forEach(sec => sec.style.display = 'none');
            document.getElementById(`section-${target}`).style.display = 'block';

            // Load specific data
            if (target === 'docs') loadDocuments();
            if (target === 'transactions') loadTransactions();
            if (target === 'metrics') loadMetrics();
        });
    });

    // File Upload Logic
    const fileInput = document.getElementById('adminFileInput');
    const dropZone = document.getElementById('dropZone');

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#6366f1';
        dropZone.style.backgroundColor = 'rgba(99, 102, 241, 0.1)';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.style.borderColor = 'var(--border-color)';
        dropZone.style.backgroundColor = 'transparent';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--border-color)';
        dropZone.style.backgroundColor = 'transparent';
        
        if (e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    function showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let iconClass = 'fas fa-info-circle';
        let title = 'Information';
        if (type === 'success') { iconClass = 'fas fa-check-circle'; title = 'Succès'; }
        if (type === 'error') { iconClass = 'fas fa-exclamation-circle'; title = 'Erreur'; }

        toast.innerHTML = `
            <div class="toast-icon"><i class="${iconClass}"></i></div>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close"><i class="fas fa-times"></i></button>
        `;

        container.appendChild(toast);

        // Close button event
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.classList.add('hiding');
            setTimeout(() => toast.remove(), 300);
        });

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (document.body.contains(toast)) {
                toast.classList.add('hiding');
                setTimeout(() => toast.remove(), 300);
            }
        }, 5000);
    }

    function handleFileUpload(file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('email', user.email);

        // Show uploading state
        dropZone.innerHTML = `<i class="fas fa-spinner fa-spin" style="font-size: 3rem; color: var(--primary-color); margin-bottom: 15px;"></i>
                              <h3>Upload de ${file.name} en cours...</h3>`;

        fetch('http://localhost:5005/api/admin/upload_and_ingest', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast("Fichier uploadé avec succès. L'ingestion se déroule en arrière-plan.", "success");
                loadDocuments();
            } else {
                showToast(data.error, "error");
            }
        })
        .catch(err => {
            showToast("Erreur réseau: " + err, "error");
        })
        .finally(() => {
            // Reset dropzone
            dropZone.innerHTML = `<i class="fas fa-file-pdf" style="font-size: 3rem; color: var(--text-dim); margin-bottom: 15px;"></i>
                                  <h3>Glissez-déposez un fichier ici</h3>
                                  <p style="color: var(--text-dim);">Supporte: PDF, TXT, DOCX, PPTX</p>
                                  <button class="login-btn" style="margin-top: 20px; width: auto; padding: 10px 20px;" onclick="document.getElementById('adminFileInput').click()">Sélectionner un fichier</button>`;
            
            // Réinitialiser le champ file pour permettre de re-sélectionner le même fichier
            const fileInput = document.getElementById('adminFileInput');
            if (fileInput) fileInput.value = '';
        });
    }

    // Load Data Functions
    window.loadDocuments = function() {
        fetch(`http://localhost:5005/api/admin/documents?email=${encodeURIComponent(user.email)}`)
        .then(res => res.json())
        .then(docs => {
            const tbody = document.getElementById('docsTableBody');
            tbody.innerHTML = '';
            docs.forEach(doc => {
                let badgeClass = 'status-badge ';
                if (doc.status === 'Ingéré') badgeClass += 'status-ingere';
                else if (doc.status === 'Erreur') badgeClass += 'status-erreur';
                else badgeClass += 'status-encours';

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>#${doc.id}</td>
                    <td>${doc.filename}</td>
                    <td>${new Date(doc.created_at).toLocaleString()}</td>
                    <td><span class="${badgeClass}">${doc.status}</span> ${doc.error_msg ? `<span style="font-size:0.8rem; color:red;">(${doc.error_msg})</span>` : ''}</td>
                `;
                tbody.appendChild(tr);
            });
        });
    }

    window.switchTab = function(tabName) {
        // Update Buttons
        document.getElementById('btn-tab-active').classList.remove('active');
        document.getElementById('btn-tab-deleted').classList.remove('active');
        document.getElementById(`btn-tab-${tabName}`).classList.add('active');

        // Update Content
        document.getElementById('tab-active').classList.remove('active');
        document.getElementById('tab-deleted').classList.remove('active');
        document.getElementById(`tab-${tabName}`).classList.add('active');
    };

    window.closeTransactionModal = function() {
        document.getElementById('transactionModal').style.display = 'none';
    };

    window.viewTransaction = function(id) {
        fetch(`/api/admin/transactions/${id}?email=${user.email}`)
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert('Erreur: ' + data.error);
                    return;
                }
                
                document.getElementById('modalTitle').innerText = data.title || 'Nouvelle conversation';
                document.getElementById('modalUser').innerText = data.user_email;
                document.getElementById('modalDate').innerText = new Date(data.timestamp).toLocaleString('fr-FR');
                
                const chatContainer = document.getElementById('modalChatHistory');
                chatContainer.innerHTML = '';
                
                if (!data.messages || data.messages.length === 0) {
                    chatContainer.innerHTML = '<div style="color:var(--text-dim); text-align:center; padding: 20px;">Aucun message dans cette session.</div>';
                } else {
                    data.messages.forEach(msg => {
                        const sender = msg.sender || msg.type || 'bot';
                        const isUser = sender === 'user';
                        const msgDiv = document.createElement('div');
                        msgDiv.style.padding = '12px 16px';
                        msgDiv.style.borderRadius = '8px';
                        msgDiv.style.maxWidth = '85%';
                        msgDiv.style.marginBottom = '10px';
                        msgDiv.style.lineHeight = '1.5';
                        msgDiv.style.fontSize = '0.95rem';
                        
                        if (isUser) {
                            msgDiv.style.background = 'var(--primary-color)';
                            msgDiv.style.color = 'white';
                            msgDiv.style.alignSelf = 'flex-end';
                        } else {
                            msgDiv.style.background = 'rgba(255,255,255,0.05)';
                            msgDiv.style.color = 'var(--text-color)';
                            msgDiv.style.alignSelf = 'flex-start';
                            msgDiv.style.border = '1px solid var(--border-color)';
                        }
                        
                        // Sécurité pour éviter l'undefined
                        const textContent = msg.text || msg.content || '';
                        
                        msgDiv.innerHTML = `<strong>${isUser ? 'Utilisateur' : 'Agent'}:</strong><br><div style="margin-top: 5px;">${textContent}</div>`;
                        chatContainer.appendChild(msgDiv);
                    });
                }
                
                document.getElementById('transactionModal').style.display = 'flex';
            })
            .catch(err => {
                console.error(err);
                alert('Erreur lors du chargement des détails.');
            });
    };

    window.loadTransactions = function() {
        if (!user || !user.email) return;

        fetch(`http://localhost:5005/api/admin/transactions?email=${user.email}`)
            .then(response => response.json())
            .then(data => {
                const tbody = document.getElementById('transTableBody');
                const deletedTbody = document.getElementById('deletedTransTableBody');
                
                if (!tbody || !deletedTbody) return;
                
                tbody.innerHTML = '';
                deletedTbody.innerHTML = '';
                
                if (data.error) {
                    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:red;">Erreur: ${data.error}</td></tr>`;
                    return;
                }

                let activeCount = 0;
                let deletedCount = 0;

                if (data.length > 0) {
                    data.forEach(trans => {
                        let displayTime = trans.timestamp;
                        try {
                            const dateObj = new Date(trans.timestamp);
                            if (!isNaN(dateObj.getTime())) {
                                displayTime = dateObj.toLocaleString('fr-FR');
                            }
                        } catch(e) {}

                        let titleHtml = trans.title || 'Nouvelle conversation';
                        
                        const rowCss = "cursor: pointer; transition: background 0.2s;";
                        const rowHover = "onmouseover=\"this.style.background='rgba(255,255,255,0.05)'\" onmouseout=\"this.style.background='transparent'\"";

                        if (trans.is_deleted === 1 || trans.is_archived === 1) {
                            // Suppression des badges à la demande de l'utilisateur
                            
                            const trHtml = `
                                <tr style="${rowCss}" ${rowHover} onclick="if(event.target.type !== 'checkbox') viewTransaction('${trans.id}')">
                                    <td style="width: 40px;" onclick="event.stopPropagation();"><input type="checkbox" class="deleted-trans-checkbox" value="${trans.id}" onclick="updateDeleteButtonVisibility()"></td>
                                    <td style="font-family: monospace; font-size: 0.9em; color: var(--text-dim);">${(trans.id || '').substring(0, 15)}...</td>
                                    <td style="font-weight: 500;">${trans.user_email}</td>
                                    <td>${titleHtml}</td>
                                    <td>${displayTime}</td>
                                </tr>
                            `;
                            
                            deletedTbody.innerHTML += trHtml;
                            deletedCount++;
                        } else {
                            const trHtml = `
                                <tr style="${rowCss}" ${rowHover} onclick="viewTransaction('${trans.id}')">
                                    <td style="font-family: monospace; font-size: 0.9em; color: var(--text-dim);">${(trans.id || '').substring(0, 15)}...</td>
                                    <td style="font-weight: 500;">${trans.user_email}</td>
                                    <td>${titleHtml}</td>
                                    <td>${displayTime}</td>
                                </tr>
                            `;
                            tbody.innerHTML += trHtml;
                            activeCount++;
                        }
                    });
                }
                
                if (activeCount === 0) {
                    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--text-dim);padding:30px;">Aucune transaction active</td></tr>`;
                }
                if (deletedCount === 0) {
                    deletedTbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--text-dim);padding:30px;">Aucune archive supprimée</td></tr>`;
                }
                
                // Update Badges
                const countActiveEl = document.getElementById('countActive');
                if (countActiveEl) countActiveEl.innerText = activeCount;
                
                const countDeletedEl = document.getElementById('countDeleted');
                if (countDeletedEl) countDeletedEl.innerText = deletedCount;
                
                // Update Global Metric
                const valTotalSessions = document.getElementById('valTotalSessions');
                if (valTotalSessions) valTotalSessions.innerText = activeCount;
            })
            .catch(err => {
                console.error("Erreur de chargement des transactions", err);
            });
    }

    let kbChartInstance = null;
    let usageChartInstance = null;

    window.loadMetrics = function() {
        fetch(`http://localhost:5005/api/admin/metrics?email=${encodeURIComponent(user.email)}`)
        .then(res => res.json())
        .then(metrics => {
            if(metrics.error) return;
            
            const usersCount = metrics.database.total_users || 0;
            const sessionsCount = metrics.database.total_sessions || 0;
            const faissCount = metrics.system && metrics.system.indices ? (metrics.system.indices.faiss.total_vectors || 0) : 0;
            const bm25Count = metrics.system && metrics.system.indices ? (metrics.system.indices.bm25.total_documents || 0) : 0;

            document.getElementById('valTotalUsers').textContent = usersCount;
            document.getElementById('valTotalSessions').textContent = sessionsCount;
            document.getElementById('valFaissDocs').textContent = faissCount;
            document.getElementById('valBm25Docs').textContent = bm25Count;

            // Mise à jour des statuts LLM
            if(metrics.system && metrics.system.llm) {
                const updateStatusCard = (id, isOnline) => {
                    const card = document.getElementById(id);
                    if (!card) return;
                    const indicator = card.querySelector('.status-indicator');
                    const text = card.querySelector('.status-text');
                    if (isOnline) {
                        indicator.className = 'status-indicator online';
                        text.innerText = 'Opérationnel';
                        text.style.color = '#10b981';
                    } else {
                        indicator.className = 'status-indicator offline';
                        text.innerText = 'Hors Ligne';
                        text.style.color = '#ef4444';
                    }
                };

                updateStatusCard('status-groq', metrics.system.llm.groq);
                updateStatusCard('status-ollama', metrics.system.llm.ollama);
                updateStatusCard('status-fallback', metrics.system.llm.has_fallback);
            }

            // Mise à jour des Ressources Matérielles
            if(metrics.hardware) {
                const hw = metrics.hardware;
                
                // CPU
                const cpuBar = document.getElementById('bar-cpu');
                const cpuTxt = document.getElementById('txt-cpu');
                if (cpuBar && cpuTxt) {
                    cpuBar.style.width = hw.cpu + '%';
                    cpuTxt.textContent = hw.cpu + '%';
                    cpuBar.style.backgroundColor = hw.cpu > 85 ? '#ef4444' : '#6366f1';
                }

                // RAM
                const ramBar = document.getElementById('bar-ram');
                const ramTxt = document.getElementById('txt-ram');
                if (ramBar && ramTxt) {
                    ramBar.style.width = hw.ram.percent + '%';
                    ramTxt.textContent = `${hw.ram.used} GB / ${hw.ram.total} GB (${hw.ram.percent}%)`;
                    ramBar.style.backgroundColor = hw.ram.percent > 85 ? '#ef4444' : '#10b981';
                }

                // DISK
                const diskBar = document.getElementById('bar-disk');
                const diskTxt = document.getElementById('txt-disk');
                if (diskBar && diskTxt) {
                    diskBar.style.width = hw.disk.percent + '%';
                    diskTxt.textContent = `${hw.disk.used} GB / ${hw.disk.total} GB (${hw.disk.percent}%)`;
                    diskBar.style.backgroundColor = hw.disk.percent > 90 ? '#ef4444' : '#f59e0b';
                }
            }

            // Mise à jour des Graphiques Chart.js
            if (typeof Chart !== 'undefined') {
                Chart.defaults.color = '#9ca3af';
                Chart.defaults.font.family = "'Inter', sans-serif";

                // Graphique Base de Connaissance
                if (kbChartInstance) {
                    kbChartInstance.data.datasets[0].data = [faissCount, bm25Count];
                    kbChartInstance.update();
                } else {
                    const ctxKb = document.getElementById('kbChart');
                    if (ctxKb) {
                        kbChartInstance = new Chart(ctxKb.getContext('2d'), {
                            type: 'doughnut',
                            data: {
                                labels: ['Vecteurs FAISS', 'Documents BM25'],
                                datasets: [{
                                    data: [faissCount, bm25Count],
                                    backgroundColor: ['#6366f1', '#10b981'],
                                    borderWidth: 0,
                                    hoverOffset: 4
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {
                                    legend: { position: 'bottom' }
                                },
                                cutout: '70%'
                            }
                        });
                    }
                }

                // Graphique Activité
                if (usageChartInstance) {
                    usageChartInstance.data.datasets[0].data = [usersCount, sessionsCount];
                    usageChartInstance.update();
                } else {
                    const ctxUsage = document.getElementById('usageChart');
                    if (ctxUsage) {
                        usageChartInstance = new Chart(ctxUsage.getContext('2d'), {
                            type: 'bar',
                            data: {
                                labels: ['Utilisateurs', 'Sessions Actives'],
                                datasets: [{
                                    label: 'Quantité',
                                    data: [usersCount, sessionsCount],
                                    backgroundColor: ['rgba(99, 102, 241, 0.7)', 'rgba(16, 185, 129, 0.7)'],
                                    borderColor: ['#6366f1', '#10b981'],
                                    borderWidth: 1,
                                    borderRadius: 4
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {
                                    legend: { display: false }
                                },
                                scales: {
                                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                                    x: { grid: { display: false } }
                                }
                            }
                        });
                    }
                }
            }
        });
    }; // Fin de loadMetrics

    window.toggleSelectAllDeleted = function(source) {
        const checkboxes = document.querySelectorAll('.deleted-trans-checkbox');
        checkboxes.forEach(cb => cb.checked = source.checked);
        updateDeleteButtonVisibility();
    };

    window.updateDeleteButtonVisibility = function() {
        const checkboxes = document.querySelectorAll('.deleted-trans-checkbox:checked');
        const btnDeleteSelected = document.getElementById('btnDeleteSelected');
        if (btnDeleteSelected) {
            btnDeleteSelected.style.display = checkboxes.length > 0 ? 'inline-block' : 'none';
            btnDeleteSelected.innerText = `Supprimer la sélection (${checkboxes.length})`;
        }
    };

    window.deleteSelectedTransactions = function() {
        const checkboxes = document.querySelectorAll('.deleted-trans-checkbox:checked');
        if (checkboxes.length === 0) return;
        
        if (!confirm(`Êtes-vous sûr de vouloir supprimer définitivement ces ${checkboxes.length} conversation(s) de la base de données ? Cette action est irréversible.`)) {
            return;
        }

        const ids = Array.from(checkboxes).map(cb => cb.value);

        fetch(`/api/admin/transactions/delete?email=${user.email}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ session_ids: ids })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert("Erreur: " + data.error);
            } else {
                showToast("Conversations supprimées avec succès.", "success");
                loadTransactions(); // Recharger le tableau
                document.getElementById('selectAllDeleted').checked = false;
                updateDeleteButtonVisibility();
            }
        })
        .catch(err => {
            console.error(err);
            alert("Erreur lors de la suppression.");
        });
    };

    // Initial load
    loadDocuments();
    
    // Auto refresh every 5 seconds for active tabs
    setInterval(() => {
        const activeNav = document.querySelector('.nav-item.active');
        if (activeNav) {
            const target = activeNav.getAttribute('data-target');
            if (target === 'docs') loadDocuments();
            if (target === 'metrics') loadMetrics();
        }
    }, 5000);

}); // Fin de DOMContentLoaded
