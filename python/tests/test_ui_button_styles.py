"""Image/WAV source contracts; no video control or rendered GTK acceptance."""
from pathlib import Path
import re
import ast

SOURCE = (Path(__file__).resolve().parents[2] / 'ui/src/hyprneuro.c').read_text()
CSS = ''.join(ast.literal_eval(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', SOURCE[SOURCE.index('/* CSS. */'):]))


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
    assert '.hn-panel button.hn-status-action, .hn-panel button.hn-status-action:hover, .hn-panel button.hn-status-action:active { min-width: 0; min-height: 0; padding: 0; margin: 0; border: 0; outline: none; background: transparent; background-image: none; box-shadow: none; }' in CSS
    assert '.hn-panel button.hn-status-action:focus-visible { outline: 1px solid #9ecbff; outline-offset: 1px; }' in CSS
    for control in ('size_toggle', 'settings_btn'):
        assert f'gtk_widget_add_css_class(a->{control}, "hn-status-action");' in SOURCE
    assert 'gtk_overlay_set_measure_overlay(GTK_OVERLAY(a->panel), a->size_toggle, FALSE);' in SOURCE


def test_exact_static_mdi_glyph_inherits_status_dimming_once():
    glyph = re.search(r'#define RESTORE_GLYPH "([^"]+)"', SOURCE).group(1)
    assert glyph == '󰯎' and ord(glyph) == 0xF0BCE
    assert 'gtk_label_new(RESTORE_GLYPH)' in SOURCE
    assert 'gtk_widget_add_css_class(size_glyph, "hn-restore-glyph");' in SOURCE
    assert SOURCE.count('gtk_widget_add_css_class(size_glyph, "dim-label")') == 1
    assert 'gtk_widget_add_css_class(a->status, "dim-label");' in SOURCE
    assert 'gtk_widget_add_css_class(a->size_toggle, "dim-label")' not in SOURCE
    assert 'gtk_widget_set_size_request(size_glyph, 16, 16);' in SOURCE
    body = re.search(r'\.hn-panel label\.hn-restore-glyph \{([^}]+)', CSS).group(1)
    assert 'font-family: "Material Design Icons";' in body and 'font-size: 16px;' in body
    assert 'color:' not in body and 'opacity:' not in body
    assert '.hn-panel button.hn-restore-action { color: inherit; }' in CSS
    assert 'gtk_widget_add_css_class(a->size_toggle, "hn-restore-action");' in SOURCE
    code = function('apply_transcript_size')
    assert 'gtk_button_set_icon_name' not in code
    assert 'go-up-symbolic' not in SOURCE and 'go-down-symbolic' not in SOURCE


def test_only_two_visible_sizes_and_control_tab_uses_same_toggle():
    assert 'typedef enum { SIZE_NORMAL, SIZE_EXPANDED } TranscriptSize;' in SOURCE
    assert 'SIZE_COMPACT' not in SOURCE
    code = function('apply_transcript_size')
    assert 'gtk_widget_set_visible(a->scroller, TRUE);' in code
    assert 'FALSE' not in code and 'margin_end' not in code
    assert 'keyval == GDK_KEY_Tab && (state & GDK_CONTROL_MASK)' in SOURCE
    assert 'gtk_event_controller_set_propagation_phase(key, GTK_PHASE_CAPTURE);' in SOURCE
    assert 'static const char *size_labels[] = {"Normal", "Expanded", NULL};' in SOURCE
    assert 'expected ? a->saved_size_token : size_names[draft]' in SOURCE
