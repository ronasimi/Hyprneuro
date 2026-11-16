"""Fixed isolated manager entry. Root comes from MAIN via LoadCredential only."""
import asyncio
from pathlib import Path
import sys
sys.dont_write_bytecode=True

# -I deliberately ignores ambient PYTHONPATH. This path is relative to the
# independently reviewed fixed entry itself, never a caller/model selector.
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    import argparse
    from hyprneuro.identity_root import load_manager_root
    class FixedParser(argparse.ArgumentParser):
        def error(self,message):
            raise PermissionError('Invalid fixed identity entry arguments')
    parser=FixedParser(description='Fixed MAIN-rooted identity entry')
    parser.add_argument('role',choices=['broker','helper'])
    parser.add_argument('--root-record',required=True,action='append')
    parser.add_argument('--generation',required=True,action='append')
    args,rest=parser.parse_known_args()
    if len(args.root_record)!=1 or len(args.generation)!=1:
        parser.error('Duplicate root input')
    rest=rest[1:] if rest[:1]==['--'] else rest
    if (args.role=='helper' and rest) or (args.role=='broker' and (not rest or rest[0]!='serve')):
        parser.error('Helper takes no app arguments; broker must serve')
    if args.role=='helper':
        # Independent process budget, including suspend and blocked event-loop/
        # persistence/metadata windows. This is ONLY the fixed activated helper,
        # never a broker/UI/owner kill and never an authority-producing timer.
        import os,threading,time
        if (os.environ.get('LISTEN_PID')!=str(os.getpid()) or os.environ.get('LISTEN_FDS')!='1'
                or os.environ.get('LISTEN_FDNAMES')!='identity-session'):
            raise PermissionError('Helper requires exact manager activation')
        deadline=time.clock_gettime_ns(time.CLOCK_BOOTTIME)+7200*1_000_000_000
        def budget():
            while time.clock_gettime_ns(time.CLOCK_BOOTTIME)<deadline:
                time.sleep(.05)
            os._exit(124)  # kernel closes helper endpoint; consumers seal FIRST
        threading.Thread(target=budget,name='identity-boottime-budget',daemon=True).start()
    policy=asyncio.run(load_manager_root(args.root_record[0],args.generation[0],args.role))
    if args.role=='helper':
        from hyprneuro.identity_transport import serve_activated
        asyncio.run(serve_activated(policy))
    else:
        from hyprneuro.sidecar import main as broker_main
        sys.argv=[sys.argv[0],*rest]
        broker_main(identity_policy=policy)


if __name__=='__main__':
    try:
        main()
    except Exception:
        from hyprneuro.trusted_control import diagnostic_rejection
        diagnostic_rejection('identity-root',PermissionError('Root entry rejected'),0)
        raise SystemExit(1)
