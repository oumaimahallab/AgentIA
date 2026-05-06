## ✅ What is WSL?

**WSL (Windows Subsystem for Linux)** allows you to run a full Linux environment inside Windows **without needing a heavy virtual machine**.

You can use it for:

*   **Development**: Run Python, Ruby, Node.js, C++, etc. in a native Linux environment.
*   **Docker**: Run containers efficiently using WSL2.
*   **Servers**: Test Apache/Nginx exactly as they behave on cloud servers.
*   **Automation**: Use Bash and Linux scripts to manage files and workflows.

***

## ✅ Main Commands You Need to Know

### **WSL Management (Run these in Windows PowerShell)**

    wsl

Opens your default Linux distribution.

    wsl -l -v

Lists all installed Linux distros and their running state.

    wsl --shutdown

Stops all Linux instances — useful for fixing stuck processes.

    wsl --update

Updates the Linux kernel to the latest version.

***

### **Linux Basics (Run these inside your Ubuntu terminal)**

    ls

List files in the current directory.

    cd <folder>

Move into a folder.

    cd ~

Return to your Linux home directory.

    cd /mnt/c/

Access your Windows \**C:\** drive from Linux.

    explorer.exe .

Open the current Linux folder in Windows File Explorer.

    sudo apt update

Refresh available software packages.

    sudo apt install <name>

Install a package (example: `sudo apt install git`).

    mkdir <name>

Create a new directory.

    pwd

Show your current path.

***

## ✅ Pro Tip: Access Linux Files from Windows

In the Windows File Explorer address bar, type:

    \\wsl$\Ubuntu

This will open your Linux filesystem like a network drive — perfect for drag‑and‑drop file management.


# Problems :
1. the airflow skips the tasks because the memory is full:
so i updated the memory of docker with :
```
[wsl2]
memory=12GB
swap=8GB      # Ajoute 8 Go de mémoire virtuelle
localhostForwarding=true
```
and before the file is updated: 
```
PS C:\Users\maup10464> wsl free -h
               total        used        free      shared  buff/cache   available
Mem:           7.4Gi       3.7Gi       3.4Gi        18Mi       464Mi       3.7Gi
```

after updating the file:
```
PS C:\Users\maup10464> wsl free -h
               total        used        free      shared  buff/cache   available
Mem:            11Gi       2.6Gi       6.9Gi        21Mi       2.4Gi       9.0Gi
Swap:          8.0Gi       1.0Mi       8.0Gi
```