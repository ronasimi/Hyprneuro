"""MAIN-only root provisioning command; never starts/installs/reloads a unit."""
import asyncio
from pathlib import Path
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    import argparse
    from hyprneuro.identity_root import guard_root
    class FixedParser(argparse.ArgumentParser):
        def error(self,message):raise PermissionError('Invalid MAIN guard arguments')
    parser=FixedParser(description='Provision independently MAIN-pinned launch root')
    for name in ['record','root-sha256','generation']:
        parser.add_argument('--'+name,required=True,action='append')
    args=parser.parse_args()
    if any(len(getattr(args,k))!=1 for k in ['record','root_sha256','generation']):
        parser.error('Duplicate MAIN input')
    asyncio.run(guard_root(args.record[0],args.root_sha256[0],args.generation[0]))


if __name__=='__main__':
    try:main()
    except Exception:
        from hyprneuro.trusted_control import diagnostic_rejection
        diagnostic_rejection('identity-root',PermissionError('MAIN guard rejected'),0)
        raise SystemExit(1)
