"""Pure assertions for private synthetic fixtures, never runtime authority."""
def require_revoked_rows(rows,root):
    # Revocation deliberately retains historical SQL rows. Require the EXACT
    # owned zeroed/revoked row, not deletion, broad filtering or any active row.
    expected=[{'task_id':'source-observer-private','app_id':'hyprneuro-parent-read',
                       'file_prefix':str(root/'owner/home/workspace'),'ops':['read'],
                       'status':'revoked','approved':False,'created_ms':0}]
    if rows!=expected:raise AssertionError('Private fixture owned revoked row mismatch')

def require_clean_result(result,root):
    require_revoked_rows(result.get('rows'),root)
    expected=dict(rows=result['rows'],live_registrations=0,published=0,observer_cleanup_confirmed=True,failures=0)
    if result!=expected:raise AssertionError('Private fixture cleanup state mismatch')


def require_unknown_channel(result,child_exit):
    # Independent outcomes: clean process exit NEVER supplies a reap/ACK receipt.
    if (type(child_exit) is not int or child_exit not in (0,1)
            or result.get('observer_cleanup_confirmed') is not False
            or result.get('live_registrations')!=0 or result.get('published')!=0
            or type(result.get('failures')) is not int or result['failures']<=0):
        raise AssertionError('Private fixture unknown channel state mismatch')
