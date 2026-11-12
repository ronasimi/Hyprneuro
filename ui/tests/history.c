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
int main(int argc, char **argv) {
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ui/reasoning-tags", reasoning_tags);
    g_test_add_func("/ui/history-ownership", history_ownership);
    g_test_add_func("/ui/adjustment-callback", adjustment_callback);
    g_test_add_func("/ui/numeric-values", numeric_values);
    g_test_add_func("/ui/busy-enter-consumed", busy_enter_consumed);
    g_test_add_func("/ui/image-bounds-snapshot", image_bounds_and_snapshot);
    return g_test_run();
}
