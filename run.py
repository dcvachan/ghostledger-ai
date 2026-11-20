import os
from ghostledger import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', '1') == '1'
    print(f"\n=======================================================")
    print(f"  GhostLedger AI - Evidence-First Reconciliation Agent")
    print(f"  Local Server: http://127.0.0.1:{port}")
    print(f"  Demo Analyst: demo_analyst (One-click Login enabled)")
    print(f"=======================================================\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
