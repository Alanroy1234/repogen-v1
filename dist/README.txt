============================================================
RepoGen - S7 Communication Tool
============================================================

This application is a self-contained Windows tool for testing Snap7 communication with Siemens S7 PLCs (both physical and simulated via NetToPLCSim).

It does NOT require Python, pip, or Node.js to be installed on the machine.

============================================================
1. INSTALL / LAUNCH
============================================================
Since this is a portable application packaged as a single executable, no installation is necessary.

Simply double-click `RepoGen-S7.exe` to launch the application.

============================================================
2. PLCSIM + NETTOPLCSIM SETUP (For Simulated PLCs)
============================================================
1. Start Siemens PLCSIM and load your project.
2. Start NetToPLCSim with Administrator privileges.
3. Configure NetToPLCSim:
   - Network IP Address: Choose the IP address of your Windows PC (e.g., 192.168.0.x).
   - Plcsim IP Address: Choose the IP address of the PLC in your Step7/TIA project.
   - Rack / Slot: Match your project (usually Rack 0, Slot 1 for S7-300, or Rack 0, Slot 1 for S7-1200/1500).
4. Start the NetToPLCSim server.
5. In RepoGen, use the Network IP Address you selected in step 3.

============================================================
3. HOW TO TEST S7 COMMUNICATION
============================================================
1. Launch RepoGen.
2. Configure IP, Rack, and Slot according to your real PLC or NetToPLCSim setup. The default port is 102.
3. Click [PING PLC] to verify network reachability.
4. Click [TEST S7 COMMUNICATION] to verify actual Snap7 communication. This will briefly connect, read the CPU state, and disconnect.
5. Click [CONNECT] to establish a persistent connection.
6. The status indicators will show "CONNECTED" and display the current CPU state.
7. Click [DISCONNECT] to close the connection.
8. Click [RECONNECT] to simulate a network drop and recovery.

============================================================
4. TROUBLESHOOTING
============================================================
- If Ping succeeds but S7 Communication fails, verify that port 102 is open and not blocked by a firewall.
- If using NetToPLCSim, ensure you are running it as Administrator.
- If you get "Connection refused", NetToPLCSim might not be running or the physical PLC is not connected.
- For S7-1200/1500, ensure "Permit access with PUT/GET communication from remote partner" is enabled in the TIA Portal hardware configuration.
