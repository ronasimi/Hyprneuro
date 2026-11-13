/* Exercise the actual UI helpers without a display or model. */
#define main hyprneuro_ui_main
#include "../src/hyprneuro.c"
#undef main

static void history_ownership(void) {
    App app = {0};
    app.history = g_ptr_array_new_with_free_func((GDestroyNotify)json_node_unref);
    for (int i = 0; i < 100; i++) {
        char *text = g_strdup_printf("turn %d — maple", i);
        push_history(&app, i % 2 ? "assistant" : "user", text);
        g_free(text);
        for (int repeat = 0; repeat < 2; repeat++) {
            char *encoded = history_to_json(&app);
            JsonParser *parser = json_parser_new();
            g_assert_true(json_parser_load_from_data(parser, encoded, -1, NULL));
            JsonArray *array = json_node_get_array(json_parser_get_root(parser));
            g_assert_cmpuint(json_array_get_length(array), ==, MIN(i + 1, MAX_HISTORY));
            JsonObject *last = json_array_get_object_element(array, json_array_get_length(array) - 1);
            char *expected = g_strdup_printf("turn %d — maple", i);
            g_assert_cmpstr(json_object_get_string_member(last, "content"), ==, expected);
            g_free(expected); g_object_unref(parser); g_free(encoded);
        }
    }
    g_ptr_array_unref(app.history);
}
static void adjustment_callback(void) {
    App app = {0};
    GtkAdjustment *adj = gtk_adjustment_new(0, 0, 1000, 1, 100, 100);
    g_object_ref_sink(adj);
    g_signal_connect(adj, "value-changed", G_CALLBACK(on_scroll_adjustment), &app);
    gtk_adjustment_set_value(adj, 100);
    g_assert_true(app.user_scrolled_up);
    gtk_adjustment_set_value(adj, 900);
    g_assert_false(app.user_scrolled_up);
    g_object_unref(adj);
}
static void numeric_values(void) {
    JsonParser *parser = json_parser_new();
    g_assert_true(json_parser_load_from_data(parser, "{\"cpu\":1.5,\"ram\":42}", -1, NULL));
    JsonNode *root = json_parser_get_root(parser);
    g_assert_cmpfloat(jnum(jmember(root, "cpu"), -1), ==, 1.5);
    g_assert_cmpfloat(jnum(jmember(root, "ram"), -1), ==, 42);
    g_assert_cmpfloat(jnum(NULL, -1), ==, -1);
    g_object_unref(parser);
}
static void image_bounds_and_snapshot(void) {
    char *directory = g_dir_make_tmp("hyprneuro-image-test-XXXXXX", NULL);
    g_assert_nonnull(directory);
    char *path = g_build_filename(directory, "image.png", NULL);
    GFile *file = g_file_new_for_path(path);
    GdkPixbuf *image = gdk_pixbuf_new(GDK_COLORSPACE_RGB, FALSE, 8, 1280, 720);
    gdk_pixbuf_fill(image, 0xff0000ff);
    g_assert_true(gdk_pixbuf_save(image, path, "png", NULL, NULL));
    g_object_unref(image);
    char *b64 = NULL, *mime = NULL;
    GdkPixbuf *preview = NULL;
    gsize length = 0;
    ImageSize size = {0};
    g_assert_true(load_image(file, &b64, &mime, &preview, &length, &size));
    g_assert_cmpint(size.width, ==, 1280); g_assert_cmpint(size.height, ==, 720);
    g_assert_cmpint(gdk_pixbuf_get_width(preview), ==, 640);
    g_assert_cmpint(gdk_pixbuf_get_height(preview), ==, 360);
    g_assert_cmpstr(mime, ==, "image/png");
    gsize decoded_length = 0, original_length = 0;
    guchar *decoded = g_base64_decode(b64, &decoded_length);
    char *original = NULL;
    g_assert_true(g_file_get_contents(path, &original, &original_length, NULL));
    g_assert_cmpuint(length, ==, original_length);
    g_assert_cmpmem(decoded, decoded_length, original, original_length);
    g_free(decoded); g_free(original); g_free(b64); g_free(mime); g_object_unref(preview);
    image = gdk_pixbuf_new(GDK_COLORSPACE_RGB, FALSE, 8, 4097, 1);
    gdk_pixbuf_fill(image, 0xff0000ff);
    g_assert_true(gdk_pixbuf_save(image, path, "png", NULL, NULL));
    g_object_unref(image);
    g_assert_false(load_image(file, &b64, &mime, &preview, &length, &size));
    g_assert_true(g_file_set_contents(path, "unsupported document", -1, NULL));
    g_assert_false(load_image(file, &b64, &mime, &preview, &length, &size));
    char *oversized = g_malloc0(5 * 1024 * 1024 + 1);
    g_assert_true(g_file_set_contents(path, oversized, 5 * 1024 * 1024 + 1, NULL));
    g_assert_false(load_image(file, &b64, &mime, &preview, &length, &size));
    g_free(oversized); g_object_unref(file);
    g_unlink(path); g_rmdir(directory); g_free(path); g_free(directory);
}
static void busy_enter_consumed(void) {
    App app = {.busy = TRUE};
    /* Busy sends must return before accessing input; no GtkTextView needed. */
    g_assert_true(on_input_key(NULL, GDK_KEY_Return, 0, 0, &app));
    g_assert_true(on_input_key(NULL, GDK_KEY_KP_Enter, 0, 0, &app));
    g_assert_false(on_input_key(NULL, GDK_KEY_a, 0, 0, &app));
}
static void reasoning_tags(void) {
    App app = {0};
    app.current_answer = g_string_new("");
    GtkTextBuffer *buf = gtk_text_buffer_new(NULL);
    create_transcript_tags(&app, buf);
    GtkTextTag *answer = app.tag_asst;
    GtkTextTag *thinking = gtk_text_tag_table_lookup(gtk_text_buffer_get_tag_table(buf), "thinking");
    render_delta(&app, buf, "check α", TRUE);
    render_delta(&app, buf, " then β", TRUE);
    render_delta(&app, buf, "Answer ✓", FALSE);
    render_delta(&app, buf, "<literal>", FALSE);
    g_assert_cmpstr(app.current_answer->str, ==, "Answer ✓<literal>");
    GtkTextIter begin, end;
    gtk_text_buffer_get_bounds(buf, &begin, &end);
    char *text = gtk_text_buffer_get_text(buf, &begin, &end, FALSE);
    g_assert_cmpstr(text, ==, "\nThinking: check α then β\nAnswer ✓<literal>");
    GtkTextIter iter;
    gtk_text_buffer_get_iter_at_offset(buf, &iter, 11);
    g_assert_true(gtk_text_iter_has_tag(&iter, thinking));
    g_assert_false(gtk_text_iter_has_tag(&iter, answer));
    gtk_text_buffer_get_iter_at_offset(buf, &iter, 25);
    g_assert_true(gtk_text_iter_has_tag(&iter, answer));
    g_assert_false(gtk_text_iter_has_tag(&iter, thinking));
    int style, weight;
    GdkRGBA *color = NULL;
    g_object_get(thinking, "style", &style, "weight", &weight, "foreground-rgba", &color, NULL);
    g_assert_cmpint(style, ==, PANGO_STYLE_ITALIC);
    g_assert_cmpint(weight, ==, PANGO_WEIGHT_NORMAL);
    g_assert_cmpfloat_with_epsilon(color->red, 184.0/255, .001);
    g_assert_cmpfloat(color->red, ==, color->green);
    g_assert_cmpfloat(color->green, ==, color->blue);
    gdk_rgba_free(color); g_free(text); g_object_unref(buf);
    g_string_free(app.current_answer, TRUE);
}
static void inference_metrics_format(void) {
    JsonParser *p = json_parser_new();
    g_assert_true(json_parser_load_from_data(p,
        "{\"prefill_tps\":12.5,\"decode_tps\":7,\"cache_hit_pct\":0}", -1, NULL));
    char *text = format_inference_metrics(json_parser_get_root(p));
    g_assert_cmpstr(text, ==, "Prefill 12.5 t/s · Decode 7.0 t/s · Hit 0.0% · Full —");
    g_free(text);
    g_assert_true(json_parser_load_from_data(p,
        "{\"prefill_tps\":true,\"decode_tps\":\"8\",\"cache_hit_pct\":101}", -1, NULL));
    text = format_inference_metrics(json_parser_get_root(p));
    g_assert_cmpstr(text, ==, "Prefill — · Decode — · Hit — · Full —");
    g_free(text);
    text = format_inference_metrics(NULL);
    g_assert_cmpstr(text, ==, "Prefill — · Decode — · Hit — · Full —");
    g_free(text);
    g_assert_true(json_parser_load_from_data(p,
        "{\"prompt_tokens_total\":20,\"prompt_tokens_evaluated\":20,\"prompt_tokens_cached\":0,\"output_tokens\":4}", -1, NULL));
    text = format_token_counts(json_parser_get_root(p));
    g_assert_nonnull(strstr(text, "Prompt total 20 · evaluated 20 · cached 0 · output 4"));
    g_free(text);
    g_assert_true(json_parser_load_from_data(p,
        "{\"prompt_tokens_total\":true,\"prompt_tokens_evaluated\":2.0,\"prompt_tokens_cached\":-1}", -1, NULL));
    text = format_token_counts(json_parser_get_root(p));
    g_assert_nonnull(strstr(text, "Prompt total — · evaluated — · cached — · output —"));
    g_free(text);
    JsonNode *nonfinite = json_node_new(JSON_NODE_VALUE);
    json_node_set_double(nonfinite, INFINITY);
    g_assert_cmpfloat(jnum(nonfinite, -1), ==, -1);
    json_node_set_double(nonfinite, NAN);
    g_assert_cmpfloat(jnum(nonfinite, -1), ==, -1);
    json_node_unref(nonfinite);
    g_object_unref(p);
}
static void put32(guchar *p, guint32 n) {
    p[0] = n; p[1] = n >> 8; p[2] = n >> 16; p[3] = n >> 24;
}
static guchar *pcm_wav(guint rate, guint channels, guint frames, gsize *length) {
    *length = 44 + frames * channels * 2;
    guchar *p = g_malloc0(*length);
    memcpy(p, "RIFF", 4); put32(p+4, *length-8); memcpy(p+8, "WAVEfmt ", 8);
    put32(p+16, 16); p[20] = 1; p[22] = channels;
    put32(p+24, rate); put32(p+28, rate*channels*2); p[32] = channels*2; p[34] = 16;
    memcpy(p+36, "data", 4); put32(p+40, *length-44);
    return p;
}
static void audio_bounds_snapshot(void) {
    gsize n;
    guchar *p = pcm_wav(24000, 1, 74880, &n);
    AudioInfo info = {0};
    g_assert_true(validate_wav(p, n, &info));
    g_assert_cmpuint(info.rate, ==, 24000);
    g_assert_cmpuint(info.channels, ==, 1);
    g_assert_cmpuint(info.frames, ==, 74880);
    g_assert_false(validate_wav(p, 0, &info));
    g_assert_false(validate_wav(p, 43, &info));
    g_assert_false(validate_wav(p, n-1, &info));
    guint offsets[] = {0,4,8,12,16,20,22,24,28,32,34,36,40};
    for (guint i = 0; i < G_N_ELEMENTS(offsets); i++) {
        p[offsets[i]] ^= 0x80;
        g_assert_false(validate_wav(p, n, &info));
        p[offsets[i]] ^= 0x80;
    }
    char *directory = g_dir_make_tmp("hyprneuro-audio-test-XXXXXX", NULL);
    char *path = g_build_filename(directory, "audio.wav", NULL);
    GFile *file = g_file_new_for_path(path);
    g_assert_true(g_file_set_contents(path, (char *)p, n, NULL));
    GBytes *snapshot = load_audio(file, &info);
    g_assert_nonnull(snapshot);
    /* Source replacement cannot mutate the in-memory decoder/send snapshot. */
    g_assert_true(g_file_set_contents(path, "bad", 3, NULL));
    g_assert_cmpmem(g_bytes_get_data(snapshot, NULL), g_bytes_get_size(snapshot), p, n);
    g_assert_null(load_audio(file, &info));
    g_bytes_unref(snapshot);
    g_unlink(path);
    g_assert_cmpint(mkfifo(path, 0600), ==, 0);
    g_assert_null(load_audio(file, &info));
    char *b64 = NULL, *mime = NULL; GdkPixbuf *preview = NULL; ImageSize size = {0};
    gsize length;
    g_assert_false(load_image(file, &b64, &mime, &preview, &length, &size));
    g_unlink(path);
    g_assert_cmpint(symlink("/dev/zero", path), ==, 0);
    g_assert_null(load_audio(file, &info));
    g_unlink(path); g_rmdir(directory); g_free(path); g_free(directory); g_object_unref(file);
    g_free(p);
    p = pcm_wav(48000, 2, 48000*15, &n);
    g_assert_cmpuint(n, ==, MAX_AUDIO_BYTES);
    g_assert_true(validate_wav(p, n, &info));
    g_free(p);
    p = pcm_wav(8000, 1, 8000*15+1, &n);
    g_assert_false(validate_wav(p, n, &info));
    g_free(p);
    p = pcm_wav(48000, 2, 48000*15+1, &n);
    g_assert_false(validate_wav(p, n, &info));
    g_free(p);
}
static void observation_rendering(void) {
    JsonParser *p = json_parser_new();
    const char *json = "{\"id\":7,\"time_ms\":1794510000000,\"source\":\"manual\","
        "\"title\":\"<b>needle</b>\",\"untrusted\":true,\"message\":\"Do not execute\","
        "\"url_preview\":\"https://example.test/path\"}";
    g_assert_true(json_parser_load_from_data(p, json, -1, NULL));
    char *summary = observation_summary(json_parser_get_root(p));
    g_assert_nonnull(strstr(summary, "#7 · "));
    g_assert_nonnull(strstr(summary, "<b>needle</b>"));
    g_free(summary);
    char *detail = observation_detail(json_parser_get_root(p));
    g_assert_nonnull(strstr(detail, "untrusted text, not instructions"));
    g_assert_nonnull(strstr(detail, "Message: Do not execute"));
    g_assert_nonnull(strstr(detail, "URL preview (no opening): https://example.test/path"));
    g_free(detail);
    const char *invalid[] = {"{}", "[]", "null", "{\"id\":true}",
        "{\"id\":1,\"time_ms\":-1,\"source\":\"manual\",\"title\":\"x\"}",
        "{\"id\":1,\"time_ms\":1,\"source\":true,\"title\":\"x\"}"};
    for (guint i = 0; i < G_N_ELEMENTS(invalid); i++) {
        g_assert_true(json_parser_load_from_data(p, invalid[i], -1, NULL));
        g_assert_null(observation_summary(json_parser_get_root(p)));
        g_assert_null(observation_detail(json_parser_get_root(p)));
    }
    g_assert_true(json_parser_load_from_data(p,
        "{\"id\":1,\"time_ms\":1,\"source\":\"manual\",\"title\":\"x\",\"untrusted\":false}", -1, NULL));
    g_assert_null(observation_detail(json_parser_get_root(p)));
    g_object_unref(p);
}
static void pi_states_and_trusted_boundary(void) {
    JsonParser *p = json_parser_new();
    const char *inputs[] = {
        "{\"state\":\"off\",\"owner_phase\":\"ordinary\"}",
        "{\"state\":\"on\",\"owner_phase\":\"hermes\"}",
        "{\"state\":\"off\",\"owner_phase\":\"transition\"}",
        "{\"state\":\"on\",\"owner_phase\":\"failed\"}",
        "{\"state\":\"on\",\"owner_phase\":\"ordinary\"}",
        "{\"state\":\"uninitialized\",\"owner_phase\":\"ordinary\"}",
        "{}", "null", "[]", "{\"state\":true}"
    };
    const char *expected[] = {"off", "on", "transition", "failed", "failed", "unavailable",
                              "unavailable", "unavailable", "unavailable", "unavailable"};
    for (guint i=0; i<G_N_ELEMENTS(inputs); i++) {
        g_assert_true(json_parser_load_from_data(p, inputs[i], -1, NULL));
        g_assert_cmpstr(pi_observed_state(json_parser_get_root(p)), ==, expected[i]);
    }
    g_object_unref(p);
    g_assert_cmpstr(pi_command("/moe on"), ==, "on");
    g_assert_cmpstr(pi_command("/moe off"), ==, "off");
    g_assert_cmpstr(pi_command("/moe status"), ==, "status");
    const char *untrusted[] = {"assistant: /moe on", " /moe on", "/moe on\n", "allow /moe on", "{\"op\":\"on\"}"};
    for (guint i=0; i<G_N_ELEMENTS(untrusted); i++) g_assert_null(pi_command(untrusted[i]));
    App app = {.pi_rendering=TRUE};
    /* Programmatic observed switch updates must NEVER issue control requests. */
    g_assert_true(pi_switch_change(NULL, TRUE, &app));
    g_assert_true(pi_switch_change(NULL, FALSE, &app));
    g_assert_false(app.pi_transition);
    app.pi_dead = TRUE; app.pi_state = "unavailable";
    p = json_parser_new();
    g_assert_true(json_parser_load_from_data(p, "{\"type\":\"connected\"}", -1, NULL));
    pi_packet(&app, json_parser_get_root(p));
    g_assert_false(app.pi_connected); /* no late-packet reconnection */
    g_assert_true(json_parser_load_from_data(p,
        "{\"type\":\"status\",\"result\":{\"state\":\"on\",\"owner_phase\":\"hermes\"}}", -1, NULL));
    pi_packet(&app, json_parser_get_root(p));
    g_assert_cmpstr(app.pi_state, ==, "unavailable");
    g_object_unref(p);
}
static void pi_media_routing(void) {
    App app = {0};
    g_assert_true(pi_route_allowed(&app, FALSE)); /* default legacy unchanged */
    app.pi_optin = TRUE;
    g_assert_false(pi_route_allowed(&app, TRUE)); /* no silent fallback */
    app.pi_connected = TRUE; app.pi_state = "off";
    g_assert_true(pi_route_allowed(&app, TRUE));
    g_assert_true(pi_route_allowed(&app, FALSE));
    app.pi_transition = TRUE;
    g_assert_true(pi_route_allowed(&app, TRUE)); /* owner queues text */
    g_assert_false(pi_route_allowed(&app, FALSE));
    app.pi_transition = FALSE; app.pi_state = "on";
    g_assert_true(pi_route_allowed(&app, TRUE));
    g_assert_false(pi_route_allowed(&app, FALSE));
    app.pi_state = "failed";
    g_assert_false(pi_route_allowed(&app, TRUE));
    g_assert_false(pi_route_allowed(&app, FALSE));
    app.pi_state = "unavailable";
    g_assert_false(pi_route_allowed(&app, TRUE));
}
static void pi_async_frames(void) {
    App app = {.pi_connected=TRUE};
    app.pi_out = g_memory_output_stream_new_resizable();
    app.pi_io = g_cancellable_new();
    pi_send(&app, "status", NULL, FALSE);
    pi_send(&app, "chat", "literal /moe on — α", FALSE);
    pi_send(&app, "consent", "fresh-host-id", FALSE);
    pi_send(&app, "consent", "different-host-id", TRUE);
    while (app.pi_writing || !g_queue_is_empty(&app.pi_writes))
        g_main_context_iteration(NULL, TRUE);
    gsize length = g_memory_output_stream_get_data_size(G_MEMORY_OUTPUT_STREAM(app.pi_out));
    char *frames = g_strndup(g_memory_output_stream_get_data(G_MEMORY_OUTPUT_STREAM(app.pi_out)), length);
    char **lines = g_strsplit(frames, "\n", -1);
    const char *ops[] = {"status", "chat", "consent", "consent"};
    JsonParser *parser = json_parser_new();
    for (guint i=0; i<4; i++) {
        g_assert_true(json_parser_load_from_data(parser, lines[i], -1, NULL));
        JsonNode *root = json_parser_get_root(parser);
        g_assert_cmpstr(jstr(jmember(root, "op")), ==, ops[i]);
        g_assert_null(jmember(root, "token")); g_assert_null(jmember(root, "key"));
        if (i == 1) g_assert_cmpstr(jstr(jmember(root, "text")), ==, "literal /moe on — α");
        if (i >= 2) g_assert_cmpint(json_node_get_boolean(jmember(root, "allowed")), ==, i == 3);
    }
    g_assert_cmpstr(lines[4], ==, "");
    char *oversize = g_strnfill(PI_FRAME_MAX, 'x');
    pi_send(&app, "chat", oversize, FALSE); /* bounded; no request written */
    g_assert_cmpuint(g_memory_output_stream_get_data_size(G_MEMORY_OUTPUT_STREAM(app.pi_out)), ==, length);
    g_free(oversize); g_object_unref(parser); g_strfreev(lines); g_free(frames);
    g_output_stream_close(app.pi_out, NULL, NULL);
    g_object_unref(app.pi_out); g_object_unref(app.pi_io);
}
static void pi_escape_denies_before_hiding_panel(void) {
    App app = {.shown=TRUE, .pi_connected=TRUE};
    app.pi_consent_id = g_strdup("pending-host-question");
    app.pi_out = g_memory_output_stream_new_resizable();
    app.pi_io = g_cancellable_new();
    /* No GtkStack/window exists: the pending-question path must return before
     * settings navigation/hide and works even when the layer retains focus. */
    g_assert_true(on_key(NULL, GDK_KEY_Escape, 0, 0, &app));
    g_assert_true(app.shown);
    g_assert_null(app.pi_consent_id);
    while (app.pi_writing || !g_queue_is_empty(&app.pi_writes))
        g_main_context_iteration(NULL, TRUE);
    gsize length = g_memory_output_stream_get_data_size(G_MEMORY_OUTPUT_STREAM(app.pi_out));
    JsonParser *p = json_parser_new();
    g_assert_true(json_parser_load_from_data(p,
        g_memory_output_stream_get_data(G_MEMORY_OUTPUT_STREAM(app.pi_out)), length, NULL));
    JsonNode *root = json_parser_get_root(p);
    g_assert_cmpstr(jstr(jmember(root, "op")), ==, "consent");
    g_assert_cmpstr(jstr(jmember(root, "answer_id")), ==, "pending-host-question");
    g_assert_false(json_node_get_boolean(jmember(root, "allowed")));
    g_object_unref(p);
    g_output_stream_close(app.pi_out, NULL, NULL);
    g_object_unref(app.pi_out); g_object_unref(app.pi_io);
}
int main(int argc, char **argv) {
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ui/pi-escape-denies-before-hide", pi_escape_denies_before_hiding_panel);
    g_test_add_func("/ui/pi-async-frames", pi_async_frames);
    g_test_add_func("/ui/pi-state-boundary", pi_states_and_trusted_boundary);
    g_test_add_func("/ui/pi-media-routing", pi_media_routing);
    g_test_add_func("/ui/observation-rendering", observation_rendering);
    g_test_add_func("/ui/audio-bounds-snapshot", audio_bounds_snapshot);
    g_test_add_func("/ui/inference-metrics", inference_metrics_format);
    g_test_add_func("/ui/reasoning-tags", reasoning_tags);
    g_test_add_func("/ui/history-ownership", history_ownership);
    g_test_add_func("/ui/adjustment-callback", adjustment_callback);
    g_test_add_func("/ui/numeric-values", numeric_values);
    g_test_add_func("/ui/busy-enter-consumed", busy_enter_consumed);
    g_test_add_func("/ui/image-bounds-snapshot", image_bounds_and_snapshot);
    return g_test_run();
}
