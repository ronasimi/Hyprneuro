"""Image/WAV source contracts; no video control or rendered GTK acceptance."""
from pathlib import Path
import re

SOURCE = (Path(__file__).resolve().parents[2] / 'ui/src/hyprneuro.c').read_text()
CSS = ''.join(re.findall(r'"([^"\n]*)"', SOURCE[SOURCE.index('/* CSS. */'):]))


def function(name):
    # Match definitions, not forward declarations.
    return re.search(r'static void ' + name + r'\([^;{]*\) \{.*?\n}', SOURCE, re.S).group()


def test_scoped_shadow_free_transparent_removal_states():
    rules = {selectors.strip(): body for selectors, body in re.findall(r'([^{}]+)\{([^{}]+)\}', CSS)}
    assert 'box-shadow: none;' in rules['.hn-panel button, .hn-panel button:hover, .hn-panel button:active']
    body = rules['.hn-panel button.hn-attachment-remove, .hn-panel button.hn-attachment-remove:hover, .hn-panel button.hn-attachment-remove:active']
    for declaration in ('background: transparent;', 'background-image: none;', 'border: 0;',
                        'outline: none;', 'box-shadow: none;', 'min-width: 32px;',
                        'min-height: 32px;', 'padding: 4px;'):
        assert declaration in body
    assert 'outline: 1px solid #9ecbff;' in rules['.hn-panel button.hn-attachment-remove:focus-visible']
    assert 'outline-offset: 1px;' in rules['.hn-panel button.hn-attachment-remove:focus-visible']


def test_existing_image_wav_controls_keep_removal_and_accessibility():
    for name in ('attach_audio', 'on_file_dialog_open'):
        code = function(name)
        assert '"window-close-symbolic"' in code
        assert '"hn-attachment-remove"' in code
        assert '"Remove attachment (also removes it from submission)"' in code
        assert 'G_CALLBACK(on_attachment_remove)' in code
    assert SOURCE.count('"hn-attachment-remove"') == 2
    assert 'clear_attachments(data);' in function('on_attachment_remove')
    cleanup = function('clear_attachments')
    for statement in ('gtk_media_stream_pause(a->audio_stream);',
                      'gtk_media_file_clear(GTK_MEDIA_FILE(a->audio_stream));',
                      'g_clear_object(&a->audio_stream);',
                      'g_ptr_array_set_size(a->attachments, 0);',
                      'g_clear_pointer(&a->attachment_b64, g_free);',
                      'g_clear_pointer(&a->attachment_mime, g_free);'):
        assert statement in cleanup


def test_separate_transparent_status_actions_and_focus_remain():
    assert '.hn-panel button.hn-status-action { min-width: 0; min-height: 0; padding: 0; margin: 0; border: 0; outline: none; background: transparent; box-shadow: none; }' in CSS
    assert '.hn-panel button.hn-status-action:focus-visible { outline: 1px solid #9ecbff; outline-offset: 1px; }' in CSS
    for control in ('size_toggle', 'settings_btn'):
        assert f'gtk_widget_add_css_class(a->{control}, "hn-status-action");' in SOURCE
    assert 'gtk_overlay_set_measure_overlay(GTK_OVERLAY(a->panel), a->size_toggle, FALSE);' in SOURCE
