document.addEventListener("DOMContentLoaded", () => {
    // Elements - Connection
    const ipInput = document.getElementById("ip-address");
    const rackInput = document.getElementById("rack");
    const slotInput = document.getElementById("slot");
    const portInput = document.getElementById("port");
    
    const btnPing = document.getElementById("btn-ping");
    const btnTestS7 = document.getElementById("btn-test-s7");
    const btnConnect = document.getElementById("btn-connect");
    const btnDisconnect = document.getElementById("btn-disconnect");
    const btnReconnect = document.getElementById("btn-reconnect");
    
    const indicator = document.getElementById("connection-indicator");
    const s7StateEl = document.getElementById("s7-state");
    const cpuStateEl = document.getElementById("cpu-state");
    const pingStateEl = document.getElementById("ping-state");
    const s7TestStateEl = document.getElementById("s7-test-state");
    
    const logList = document.getElementById("log-list");

    // Elements - Tabs
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    // Elements - Tag Tables
    const tableSelect = document.getElementById("tag-table-select");
    const btnNewTable = document.getElementById("btn-new-table");
    const btnDeleteTable = document.getElementById("btn-delete-table");
    const btnTogglePoll = document.getElementById("btn-toggle-poll");
    const btnAddTag = document.getElementById("btn-add-tag");
    const tagsTbody = document.getElementById("tags-tbody");

    // Elements - Modals
    const modals = document.querySelectorAll(".modal");
    const btnCloseModals = document.querySelectorAll(".btn-close-modal");
    
    // Modal - Table
    const modalTable = document.getElementById("modal-table");
    const btnSaveTable = document.getElementById("btn-save-table");
    const tableNameInput = document.getElementById("modal-table-name");
    const tableDescInput = document.getElementById("modal-table-desc");

    // Modal - Tag
    const modalTag = document.getElementById("modal-tag");
    const btnSaveTag = document.getElementById("btn-save-tag");
    const tagAreaSelect = document.getElementById("modal-tag-area");
    const groupDbNumber = document.getElementById("group-db-number");
    
    // Modal - Write
    const modalWrite = document.getElementById("modal-write");
    const btnExecuteWrite = document.getElementById("btn-execute-write");
    const writeWarning = document.getElementById("write-warning");
    
    // State
    let pollInterval = null;
    let isConnected = false;
    let activeTableId = null;
    let isPollingTags = false;
    let tagPollInterval = null;

    // Helper: Wait for pywebview API
    const waitForApi = () => {
        return new Promise((resolve) => {
            if (window.pywebview && window.pywebview.api) {
                resolve(window.pywebview.api);
            } else {
                window.addEventListener('pywebviewready', () => {
                    resolve(window.pywebview.api);
                });
            }
        });
    };

    // --- Tab Logic ---
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            document.getElementById(btn.dataset.target).classList.add("active");
        });
    });

    // --- Modal Logic ---
    const openModal = (modal) => modal.classList.add("active");
    const closeModal = (modal) => modal.classList.remove("active");
    
    btnCloseModals.forEach(btn => {
        btn.addEventListener("click", (e) => {
            const modal = e.target.closest(".modal");
            if(modal) closeModal(modal);
        });
    });

    tagAreaSelect.addEventListener("change", (e) => {
        groupDbNumber.style.display = e.target.value === "DB" ? "block" : "none";
    });

    // --- Connection Logic ---
    const getConfig = () => ({
        ip: ipInput.value,
        rack: parseInt(rackInput.value, 10),
        slot: parseInt(slotInput.value, 10),
        port: parseInt(portInput.value, 10)
    });

    const updateUIState = (status) => {
        if (!status) return;

        indicator.textContent = status.state;
        indicator.className = `status-badge ${status.state.toLowerCase().replace(' ', '-')}`;
        
        let stateText = status.state;
        if (status.last_s7_success_time && status.state === "CONNECTED") {
            stateText += ` (Last success: ${status.last_s7_success_time})`;
        }
        s7StateEl.textContent = stateText;
        
        if (status.cpu_state_error) {
            cpuStateEl.innerHTML = `${status.cpu_state}<br><span style="font-size: 0.8em; color: var(--error-color, #ff4c4c);">Error: ${status.cpu_state_error}</span>`;
            cpuStateEl.className = `value unknown`;
        } else {
            cpuStateEl.textContent = status.cpu_state;
            cpuStateEl.className = `value ${status.cpu_state.toLowerCase()}`;
        }
        
        isConnected = status.state === "CONNECTED";
        
        if (isConnected) {
            btnConnect.disabled = true;
            btnDisconnect.disabled = false;
            btnReconnect.disabled = false;
        } else {
            btnConnect.disabled = false;
            btnDisconnect.disabled = true;
            btnReconnect.disabled = true;
        }

        renderLogs(status.diagnostics);
    };

    const renderLogs = (diagnostics) => {
        logList.innerHTML = '';
        diagnostics.forEach(log => {
            const li = document.createElement('li');
            li.innerHTML = `
                <span class="log-time">${log.time}</span>
                <span class="log-op">${log.operation}</span>
                <span class="log-status ${log.status}">${log.status}</span>
                <span class="log-details">${log.details}</span>
            `;
            logList.appendChild(li);
        });
        const container = document.querySelector('.log-container');
        container.scrollTop = container.scrollHeight;
    };

    btnPing.addEventListener("click", async () => {
        const api = await waitForApi();
        const conf = getConfig();
        pingStateEl.textContent = "TESTING...";
        pingStateEl.className = "value";
        const res = await api.ping(conf.ip, conf.rack, conf.slot, conf.port);
        if (res.success) {
            pingStateEl.textContent = `PASS (${res.latency}ms)`;
            pingStateEl.className = "value pass";
        } else {
            pingStateEl.textContent = `FAIL`;
            pingStateEl.className = "value fail";
        }
        pollStatus();
    });

    btnTestS7.addEventListener("click", async () => {
        const api = await waitForApi();
        const conf = getConfig();
        s7TestStateEl.textContent = "TESTING...";
        s7TestStateEl.className = "value";
        const res = await api.test_s7_communication(conf.ip, conf.rack, conf.slot, conf.port);
        if (res.success) {
            s7TestStateEl.textContent = `PASS (${res.latency}ms)`;
            s7TestStateEl.className = "value pass";
            if (res.cpu_state_error) {
                cpuStateEl.innerHTML = `${res.cpu_state}<br><span style="font-size: 0.8em; color: var(--error-color, #ff4c4c);">Error: ${res.cpu_state_error}</span>`;
                cpuStateEl.className = `value unknown`;
            } else {
                cpuStateEl.textContent = res.cpu_state;
                cpuStateEl.className = `value ${res.cpu_state.toLowerCase()}`;
            }
        } else {
            s7TestStateEl.textContent = `FAIL`;
            s7TestStateEl.className = "value fail";
        }
        pollStatus();
    });

    btnConnect.addEventListener("click", async () => {
        const api = await waitForApi();
        const conf = getConfig();
        btnConnect.disabled = true;
        indicator.textContent = "CONNECTING...";
        await api.connect(conf.ip, conf.rack, conf.slot, conf.port);
        pollStatus();
    });

    btnDisconnect.addEventListener("click", async () => {
        const api = await waitForApi();
        btnDisconnect.disabled = true;
        await api.disconnect();
        pollStatus();
    });

    btnReconnect.addEventListener("click", async () => {
        const api = await waitForApi();
        const conf = getConfig();
        btnReconnect.disabled = true;
        indicator.textContent = "RECONNECTING...";
        await api.reconnect(conf.ip, conf.rack, conf.slot, conf.port);
        pollStatus();
    });

    const pollStatus = async () => {
        const api = await waitForApi();
        const status = await api.get_status();
        updateUIState(status);
    };

    pollInterval = setInterval(pollStatus, 150);

    // --- Tag Tables Logic ---
    const tableListUl = document.getElementById("table-list");
    const btnNewTableSidebar = document.getElementById("btn-new-table-sidebar");
    
    btnNewTableSidebar.addEventListener("click", () => {
        tableNameInput.value = "";
        tableDescInput.value = "";
        openModal(modalTable);
    });

    const loadTables = async () => {
        const api = await waitForApi();
        const tables = await api.get_all_tables();
        
        const currentVal = tableSelect.value;
        tableSelect.innerHTML = '<option value="">Select a Table...</option>';
        tableListUl.innerHTML = '';
        
        tables.forEach(t => {
            const opt = document.createElement("option");
            opt.value = t.id;
            opt.textContent = t.name;
            tableSelect.appendChild(opt);
            
            const li = document.createElement("li");
            li.textContent = t.name;
            li.dataset.id = t.id;
            if (t.id == activeTableId) li.classList.add("active");
            
            li.addEventListener("click", async () => {
                tableSelect.value = t.id;
                tableSelect.dispatchEvent(new Event('change'));
            });
            tableListUl.appendChild(li);
        });
        
        if (tables.length > 0) {
            let targetId = null;
            if (currentVal && tables.find(t => t.id == currentVal)) {
                targetId = currentVal;
            } else if (tables[0]) {
                targetId = tables[0].id;
            }
            
            if (targetId) {
                tableSelect.value = targetId;
                activeTableId = parseInt(targetId, 10);
                btnAddTag.disabled = false;
                btnDeleteTable.disabled = false;
                btnTogglePoll.disabled = false;
                
                document.querySelectorAll("#table-list li").forEach(li => {
                    li.classList.remove("active");
                    if (li.dataset.id == activeTableId) li.classList.add("active");
                });
                
                await api.set_active_table(activeTableId);
                await loadTags();
            }
        } else {
            activeTableId = null;
            btnAddTag.disabled = true;
            btnDeleteTable.disabled = true;
            btnTogglePoll.disabled = true;
            tagsTbody.innerHTML = '<tr><td colspan="8" class="text-center">No tag tables yet. Create your first tag table.</td></tr>';
        }
    };

    const loadTags = async () => {
        if (!activeTableId) return;
        const api = await waitForApi();
        const tags = await api.get_tags_for_table(activeTableId);
        
        tagsTbody.innerHTML = '';
        if (tags.length === 0) {
            tagsTbody.innerHTML = '<tr><td colspan="8" class="text-center">No tags defined</td></tr>';
            return;
        }
        
        tags.forEach(t => {
            const tr = document.createElement("tr");
            tr.id = `tag-row-${t.id}`;
            
            let fullAddr = t.area;
            if (t.area === "DB") {
                let prefix = "";
                if (t.data_type === "BOOL") prefix = "DBX";
                else if (t.data_type === "BYTE" || t.data_type === "SINT" || t.data_type === "USINT") prefix = "DBB";
                else if (t.data_type === "INT" || t.data_type === "UINT" || t.data_type === "WORD") prefix = "DBW";
                else if (t.data_type === "DINT" || t.data_type === "UDINT" || t.data_type === "DWORD" || t.data_type === "REAL") prefix = "DBD";
                
                let cleanAddr = t.address;
                if (t.data_type !== "BOOL" && cleanAddr.includes(".0")) {
                    cleanAddr = cleanAddr.split(".")[0];
                }
                
                fullAddr += `${t.db_number}.${prefix}${cleanAddr}`;
            } else {
                let prefix = "";
                if (t.data_type === "BYTE" || t.data_type === "SINT" || t.data_type === "USINT") prefix = "B";
                else if (t.data_type === "INT" || t.data_type === "UINT" || t.data_type === "WORD") prefix = "W";
                else if (t.data_type === "DINT" || t.data_type === "UDINT" || t.data_type === "DWORD" || t.data_type === "REAL") prefix = "D";
                
                // If the user included the bit for a non-BOOL (e.g. 0.0 for MD0), let's strip the .0 for display
                let cleanAddr = t.address;
                if (t.data_type !== "BOOL" && cleanAddr.includes(".0")) {
                    cleanAddr = cleanAddr.split(".")[0];
                }
                
                fullAddr += `${prefix}${cleanAddr}`;
            }
            
            tr.innerHTML = `
                <td>${t.name}</td>
                <td>${fullAddr}</td>
                <td>${t.data_type}</td>
                <td>${t.access_mode}</td>
                <td class="tag-val">---</td>
                <td class="tag-qual">---</td>
                <td class="tag-lat">---</td>
                <td>
                    <button class="btn btn-small secondary btn-edit-tag" data-id="${t.id}" data-json='${JSON.stringify(t)}'>Edit</button>
                    ${t.access_mode === "Read/Write" ? `<button class="btn btn-small primary btn-write-tag" data-id="${t.id}" data-area="${t.area}">Write</button>` : ''}
                    <button class="btn btn-small danger btn-del-tag" data-id="${t.id}">Del</button>
                </td>
            `;
            tagsTbody.appendChild(tr);
        });

        // Attach tag actions
        document.querySelectorAll(".btn-del-tag").forEach(b => {
            b.addEventListener("click", async (e) => {
                if (confirm("Delete this tag?")) {
                    await api.delete_tag(parseInt(e.target.dataset.id, 10));
                    loadTags();
                }
            });
        });

        document.querySelectorAll(".btn-write-tag").forEach(b => {
            b.addEventListener("click", (e) => {
                const tagId = e.target.dataset.id;
                const tagArea = e.target.dataset.area;
                const tr = document.getElementById(`tag-row-${tagId}`);
                const tagName = tr.children[0].textContent;
                const tagAddr = tr.children[1].textContent;
                
                document.getElementById("write-tag-id").value = tagId;
                document.getElementById("write-tag-area").value = tagArea;
                document.getElementById("write-tag-info").textContent = `Writing to ${tagName} (${tagAddr})`;
                document.getElementById("write-tag-value").value = "";
                
                writeWarning.style.display = tagArea === "Q" ? "block" : "none";
                openModal(modalWrite);
            });
        });

        document.querySelectorAll(".btn-edit-tag").forEach(b => {
            b.addEventListener("click", (e) => {
                const t = JSON.parse(e.target.dataset.json);
                document.getElementById("modal-tag-title").textContent = "Edit Tag";
                document.getElementById("modal-tag-id").value = t.id;
                document.getElementById("modal-tag-name").value = t.name;
                document.getElementById("modal-tag-area").value = t.area;
                document.getElementById("modal-tag-db-number").value = t.db_number || 1;
                document.getElementById("modal-tag-type").value = t.data_type;
                document.getElementById("modal-tag-address").value = t.address;
                document.getElementById("modal-tag-access").value = t.access_mode;
                
                groupDbNumber.style.display = t.area === "DB" ? "block" : "none";
                openModal(modalTag);
            });
        });
    };

    // Table Selection
    tableSelect.addEventListener("change", async (e) => {
        const val = e.target.value;
        const api = await waitForApi();
        if (val) {
            activeTableId = parseInt(val, 10);
            btnAddTag.disabled = false;
            btnDeleteTable.disabled = false;
            btnTogglePoll.disabled = false;
            
            // Update sidebar highlighting
            document.querySelectorAll("#table-list li").forEach(li => {
                li.classList.remove("active");
                if (li.dataset.id == activeTableId) li.classList.add("active");
            });
            
            await api.set_active_table(activeTableId);
            loadTags();
        } else {
            activeTableId = null;
            btnAddTag.disabled = true;
            btnDeleteTable.disabled = true;
            btnTogglePoll.disabled = true;
            
            // Update sidebar highlighting
            document.querySelectorAll("#table-list li").forEach(li => li.classList.remove("active"));
            
            tagsTbody.innerHTML = '<tr><td colspan="8" class="text-center">Select or create a table to view tags</td></tr>';
            await api.set_active_table(null);
        }
    });

    // New Table
    btnNewTable.addEventListener("click", () => {
        tableNameInput.value = "";
        tableDescInput.value = "";
        openModal(modalTable);
    });

    btnSaveTable.addEventListener("click", async () => {
        const api = await waitForApi();
        const name = tableNameInput.value.trim();
        if (!name) return alert("Table name is required.");
        
        await api.create_table(name, tableDescInput.value);
        closeModal(modalTable);
        loadTables();
    });

    btnDeleteTable.addEventListener("click", async () => {
        if (!activeTableId) return;
        if (confirm("Are you sure you want to delete this tag table?")) {
            const api = await waitForApi();
            await api.delete_table(activeTableId);
            loadTables();
        }
    });

    // New Tag
    btnAddTag.addEventListener("click", () => {
        document.getElementById("modal-tag-title").textContent = "Add Tag";
        document.getElementById("modal-tag-id").value = "";
        document.getElementById("modal-tag-name").value = "";
        document.getElementById("modal-tag-area").value = "M";
        document.getElementById("modal-tag-db-number").value = "1";
        document.getElementById("modal-tag-type").value = "BOOL";
        document.getElementById("modal-tag-address").value = "0.0";
        document.getElementById("modal-tag-access").value = "Read/Write";
        groupDbNumber.style.display = "none";
        openModal(modalTag);
    });

    btnSaveTag.addEventListener("click", async () => {
        const api = await waitForApi();
        const id = document.getElementById("modal-tag-id").value;
        const name = document.getElementById("modal-tag-name").value.trim();
        const area = document.getElementById("modal-tag-area").value;
        const db_number = parseInt(document.getElementById("modal-tag-db-number").value, 10);
        const data_type = document.getElementById("modal-tag-type").value;
        const address = document.getElementById("modal-tag-address").value.trim();
        const access_mode = document.getElementById("modal-tag-access").value;

        if (!name || !address) return alert("Name and address are required.");

        if (id) {
            await api.update_tag(parseInt(id, 10), name, area, area === "DB" ? db_number : null, address, data_type, access_mode, "");
        } else {
            await api.create_tag(activeTableId, name, area, area === "DB" ? db_number : null, address, data_type, access_mode, "");
        }
        
        closeModal(modalTag);
        loadTags();
    });

    // Write Execution
    btnExecuteWrite.addEventListener("click", async () => {
        const tagId = document.getElementById("write-tag-id").value;
        const val = document.getElementById("write-tag-value").value;
        const api = await waitForApi();
        
        const oldBtnText = btnExecuteWrite.textContent;
        btnExecuteWrite.textContent = "Writing...";
        btnExecuteWrite.disabled = true;
        
        const res = await api.write_tag(parseInt(tagId, 10), val);
        
        btnExecuteWrite.textContent = oldBtnText;
        btnExecuteWrite.disabled = false;
        
        if (res.success) {
            alert("Success: " + res.message);
            closeModal(modalWrite);
        } else {
            alert("Write Failed: " + res.message);
        }
    });

    // Polling Toggle
    btnTogglePoll.addEventListener("click", async () => {
        const api = await waitForApi();
        if (!activeTableId && tableSelect.value) {
            activeTableId = parseInt(tableSelect.value, 10);
        }
        
        isPollingTags = !isPollingTags;
        await api.set_polling(isPollingTags, activeTableId);
        
        if (isPollingTags) {
            btnTogglePoll.textContent = "Stop Monitoring";
            btnTogglePoll.classList.remove("primary");
            btnTogglePoll.classList.add("danger");
            
            // UI refresh loop
            tagPollInterval = setInterval(async () => {
                const response = await api.get_live_tags();
                if (!response || !response.tags) return;
                
                const live = response.tags;
                const diag = response.diagnostics;
                
                // Update diagnostic panel if it exists
                const diagPanel = document.getElementById("read-diagnostics");
                if (diagPanel && diag) {
                    diagPanel.innerHTML = `
                        <strong>Last Poll:</strong> ${diag.last_cycle} | 
                        <strong>Attempted:</strong> ${diag.attempted} | 
                        <strong>Success:</strong> <span class="pass">${diag.success}</span> | 
                        <strong>Failed:</strong> <span class="fail">${diag.failed}</span> | 
                        <strong>Last Error:</strong> ${diag.last_error}
                    `;
                }
                
                Object.keys(live).forEach(tagId => {
                    const tr = document.getElementById(`tag-row-${tagId}`);
                    if (tr) {
                        const d = live[tagId];
                        tr.querySelector('.tag-val').textContent = d.value !== null ? d.value : '---';
                        tr.querySelector('.tag-qual').textContent = d.quality;
                        
                        let qualClass = "";
                        if (d.quality === "GOOD") qualClass = "pass";
                        else if (d.quality === "BAD") qualClass = "fail";
                        
                        tr.querySelector('.tag-qual').className = `tag-qual ${qualClass} status-badge`;
                        tr.querySelector('.tag-lat').textContent = `${d.latency}ms`;
                        
                        if (d.error) {
                            tr.querySelector('.tag-val').title = d.error;
                            tr.querySelector('.tag-val').style.color = 'var(--danger)';
                        } else {
                            tr.querySelector('.tag-val').title = d.timestamp;
                            tr.querySelector('.tag-val').style.color = '';
                        }
                    }
                });
            }, 500);
            
        } else {
            btnTogglePoll.textContent = "Start Monitoring";
            btnTogglePoll.classList.add("primary");
            btnTogglePoll.classList.remove("danger");
            clearInterval(tagPollInterval);
            
            // clear values
            document.querySelectorAll('.tag-val').forEach(el => el.textContent = '---');
            document.querySelectorAll('.tag-qual').forEach(el => {el.textContent = '---'; el.className = 'tag-qual';});
            document.querySelectorAll('.tag-lat').forEach(el => el.textContent = '---');
        }
    });

    // Init
    waitForApi().then(() => {
        loadTables();
    });
});
