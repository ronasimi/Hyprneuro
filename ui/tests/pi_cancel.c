#define _GNU_SOURCE
/* Actual production packet/completion branch, with widget boundaries mocked.
 * No display, native service, portal, inference or consent interaction. */
#include <gtk/gtk.h>
static char *status_text, *metrics_text;
static GtkTextBuffer *transcript_buffer;
static gboolean send_enabled, cancel_enabled;
static void fake_label(GtkLabel *label,const char *text) {
    char **target=(gpointer)label==(gpointer)1?&status_text:&metrics_text;
    g_free(*target);*target=g_strdup(text);
}
static void fake_sensitive(GtkWidget *widget,gboolean enabled) {
    if((gpointer)widget==(gpointer)3)send_enabled=enabled;
    if((gpointer)widget==(gpointer)4)cancel_enabled=enabled;
}
static GtkTextBuffer *fake_buffer(GtkTextView *view) { (void)view;return transcript_buffer; }
static gboolean fake_focus(GtkWidget *widget) { (void)widget;return TRUE; }
static void fake_tooltip(GtkWidget *widget,const char *text) { (void)widget;(void)text; }
#undef GTK_LABEL
#undef GTK_TEXT_VIEW
#define GTK_LABEL(x) ((GtkLabel *)(x))
#define GTK_TEXT_VIEW(x) ((GtkTextView *)(x))
#define gtk_label_set_text fake_label
#define gtk_widget_set_sensitive fake_sensitive
#define gtk_text_view_get_buffer fake_buffer
#define gtk_widget_grab_focus fake_focus
#define gtk_widget_set_tooltip_text fake_tooltip
#define main hyprneuro_ui_main
#include "../src/hyprneuro.c"
#undef main

static void packet_case(gboolean known) {
    App app={0};app.busy=TRUE;app.pi_chat=TRUE;app.pi_native_error=TRUE;
    app.status=(GtkWidget *)1;app.metrics=(GtkWidget *)2;
    app.send=(GtkWidget *)3;app.pi_cancel=(GtkWidget *)4;
    app.current_msg=g_strdup("synthetic no-tool prompt");app.current_answer=g_string_new("partial native text");
    app.history=g_ptr_array_new_with_free_func((GDestroyNotify)json_node_unref);
    transcript_buffer=gtk_text_buffer_new(NULL);gtk_text_buffer_set_text(transcript_buffer,"partial native text",-1);
    send_enabled=FALSE;cancel_enabled=TRUE;
    const char *json=known?"{\"type\":\"result\",\"op\":\"chat\",\"result\":{\"settled\":false,\"cancelled\":true,\"outcome\":\"cancelled-known\"}}":
        "{\"type\":\"error\",\"op\":\"chat\",\"error\":\"unknown\"}";
    JsonParser *parser=json_parser_new();g_assert_true(json_parser_load_from_data(parser,json,-1,NULL));
    pi_packet(&app,json_parser_get_root(parser));
    GtkTextIter start,end;gtk_text_buffer_get_bounds(transcript_buffer,&start,&end);
    char *text=gtk_text_buffer_get_text(transcript_buffer,&start,&end,FALSE);
    g_assert_nonnull(strstr(text,"partial native text"));
    g_assert_false(app.busy);g_assert_false(app.pi_chat);g_assert_true(send_enabled);g_assert_false(cancel_enabled);
    g_assert_cmpuint(app.history->len,==,0);g_assert_null(app.current_msg);g_assert_cmpuint(app.current_answer->len,==,0);
    if(known) {
        g_assert_nonnull(strstr(status_text,"cancelled"));g_assert_nonnull(strstr(metrics_text,"Cancelled"));
        g_assert_null(strstr(metrics_text,"failed"));g_assert_null(strstr(text,"[error:"));
        g_assert_nonnull(strstr(text,"[cancelled:"));g_assert_null(strstr(status_text,"settled"));
    } else {
        g_assert_nonnull(strstr(metrics_text,"Inference failed"));g_assert_nonnull(strstr(text,"[error:"));
        g_assert_null(strstr(text,"[cancelled:"));
    }
    g_free(text);g_object_unref(parser);g_object_unref(transcript_buffer);g_ptr_array_unref(app.history);
    g_string_free(app.current_answer,TRUE);g_clear_pointer(&status_text,g_free);g_clear_pointer(&metrics_text,g_free);
}
static void known_terminal(void) { packet_case(TRUE); }
static void unknown_terminal(void) { packet_case(FALSE); }
int main(int argc,char **argv) {
    g_test_init(&argc,&argv,NULL);
    g_test_add_func("/ui/pi-cancel/known-production-branch",known_terminal);
    g_test_add_func("/ui/pi-cancel/unknown-production-branch",unknown_terminal);
    return g_test_run();
}
