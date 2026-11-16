# Hyprneuro UI: transparent GTK4 layer-shell overlay (component of Hyprneuro).
# Standalone meson project so it builds independently of the Python/uv stack.
project('hyprneuro-ui', 'c',
  version: '0.1.0',
  meson_version: '>=0.60',
  default_options: [
    'c_std=c11',
    'warning_level=1',
    'buildtype=debugoptimized',
  ])

deps = [
  dependency('gtk4'),
  dependency('gtk4-layer-shell-0'),
  dependency('json-glib-1.0'),
  dependency('gio-unix-2.0'),
]

executable('hyprneuro-ui',
  'src/hyprneuro.c',
  dependencies: deps,
  link_args: ['-lm'],
  install: true)

history_test = executable('test-ui-history', 'tests/history.c', dependencies: deps)
test('ui-history', history_test)

picker_test = executable('test-ui-pi-picker', 'tests/pi_picker.c', dependencies: deps)
test('ui-pi-picker', picker_test)

cancel_test = executable('test-ui-pi-cancel', 'tests/pi_cancel.c', dependencies: deps, link_args: ['-lm'])
test('ui-pi-cancel', cancel_test)

diag_test = executable('test-ui-pi-diagnostics', 'tests/pi_diagnostics.c', dependencies: deps, link_args: ['-lm'])
test('ui-pi-diagnostics', diag_test)

# Invoked only by private Python broker tests under an isolated X11/session bus.
executable('test-ui-pi-challenge-probe', 'tests/pi_challenge_probe.c', dependencies: deps,
  link_args: ['-lm', '-Wl,--wrap=g_bus_get_sync', '-Wl,--wrap=g_dbus_connection_call_sync'])
