"""Pure assertions for private synthetic fixtures, never runtime authority."""
def require_clean_result(result,root):
    # Revocation deliberately retains historical SQL rows. Require the EXACT
    # owned zeroed/revoked row, not deletion, broad filtering or any active row.
    expected={'rows':[{'task_id':'source-observer-private','app_id':'hyprneuro-parent-read',
                       'file_prefix':str(root/'owner/home/workspace'),'ops':['read'],
                       'status':'revoked','approved':False,'created_ms':0}],
              'live_registrations':0,'published':0,'observer_cleanup_confirmed':True,'failures':0}
    if result!=expected:raise AssertionError('Private fixture cleanup state mismatch')
