#!/usr/bin/env python3
import subprocess
import json
import time
import sys
import os

proc = subprocess.Popen(
    ["/home/bashbot/iew/bin/iew-lsp"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    stdin=subprocess.PIPE,
    text=True,
    bufsize=0
)

def send_message(msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()

print("Waiting for server to initialize...")
output_lines = []
time.sleep(0.5)

send_message({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "rootUri": "file:///home/bashbot",
        "capabilities": {}
    }
})

for _ in range(50):
    if proc.poll() is not None:
        break
    line = proc.stdout.readline()
    if line:
        output_lines.append(line)
        if "capabilities" in line:
            print("Server initialized")
            break
    time.sleep(0.1)

send_message({
    "jsonrpc": "2.0",
    "method": "textDocument/didOpen",
    "params": {
        "text_document": {
            "uri": "file:///home/bashbot/test_bash.sh",
            "text": open("/home/bashbot/test_bash.sh", "r").read()
        }
    }
})

print("Document opened, waiting for diagnostics...")
time.sleep(2)

send_message({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "workspace/executeCommand",
    "params": {
        "command": "iew.workspaceReview"
    }
})

time.sleep(1)
proc.terminate()
proc.wait()

print("\n=== LSP SERVER OUTPUT ===")
for line in output_lines:
    print(line, end="")

print("\n=== END OF OUTPUT ===")
