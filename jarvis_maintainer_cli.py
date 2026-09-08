import argparse
import jarvis_maintainer_v1 as m

p = argparse.ArgumentParser()
p.add_argument("action", choices=["status", "health", "repair", "history", "rollback"])
args = p.parse_args()

if args.action == "status":
    print(m.maintainer_status())
elif args.action == "health":
    print(m.health_check())
elif args.action == "repair":
    print(m.repair_issue())
elif args.action == "history":
    print(m.recent_changes(20))
elif args.action == "rollback":
    print(m.rollback_last_change())
