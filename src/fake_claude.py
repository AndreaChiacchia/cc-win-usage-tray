import sys
import time

def main():
    # Simulate banner
    print("Welcome to Claude Code!")
    sys.stdout.flush()
    time.sleep(0.5)
    
    # Wait for commands
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        
        cmd = line.strip()
        if cmd == "/status":
            print("Logged in as testuser@example.com (Free plan)")
            print("CLI Version: 0.1.0")
            sys.stdout.flush()
        elif cmd == "/usage":
            # output usage
            print("Current session")
            print("███████████████████████████████████               70% used")
            print("Resets 1:59pm (Europe/Rome)")
            print("Current week (all models)")
            print("█████████████████████▌                            43% used")
            print("Resets Mar 20, 2:59pm (Europe/Rome)")
            sys.stdout.flush()
        elif cmd == "/exit":
            break

if __name__ == "__main__":
    main()
