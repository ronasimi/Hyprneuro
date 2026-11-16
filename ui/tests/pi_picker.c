/* The actual chooser callback, with portal/focus/pipe boundaries replaced.
 * No display, portal request, service start, model or consent is exercised. */
#include <gtk/gtk.h>
#include <gtk4-layer-shell/gtk4-layer-shell.h>
#include <string.h>
typedef struct {
    GtkWindow *win;
    gboolean closing;
    gpointer pi_process;
    gboolean shown, busy, pi_optin, pi_dead, pi_selecting;
    GCancellable *picker_cancel;
    char *pi_connect_error;
} App;
static App *app_ref(App *a) { return a; } /* stack fixture, no actual async lifetime */
static void app_unref(App *a) { (void)a; }
G_DEFINE_AUTOPTR_CLEANUP_FUNC(App, app_unref)
static void pi_start(App *a) { a->pi_process=(gpointer)1; }
static GtkFileDialog *pending;
static GAsyncReadyCallback callback;
static gpointer callback_data;
static guint requests, sends, focus_changes;
static GtkLayerShellKeyboardMode focus_mode;
static char *status, *sent_root;
static void set_status(App *a, const char *text) { (void)a; g_free(status); status=g_strdup(text); }
static void pi_route_update(App *a) { (void)a; }
static void pi_render(App *a) { (void)a; }
static void pi_send(App *a, const char *op, const char *root, gboolean allowed) {
    (void)a; g_assert_cmpstr(op, ==, "connect"); g_assert_false(allowed);
    sends++; g_free(sent_root); sent_root=g_strdup(root);
}
static void fake_focus(GtkWindow *win, GtkLayerShellKeyboardMode mode) {
    g_assert_nonnull(win); focus_changes++; focus_mode=mode;
}
static void fake_select(GtkFileDialog *dialog, GtkWindow *parent, GCancellable *cancel,
                        GAsyncReadyCallback ready, gpointer data) {
    g_assert_null(parent); g_assert_true(G_IS_CANCELLABLE(cancel));
    requests++; pending=g_object_ref(dialog); callback=ready; callback_data=data;
}
static GFile *fake_finish(GtkFileDialog *dialog, GAsyncResult *result, GError **error) {
    g_assert_true(g_task_is_valid(result, dialog)); return g_task_propagate_pointer(G_TASK(result), error);
}
#define gtk_layer_set_keyboard_mode fake_focus
#define gtk_file_dialog_select_folder fake_select
#define gtk_file_dialog_select_folder_finish fake_finish
#include "../src/pi-picker.inc"
static void complete(GFile *file, GError *error) {
    GTask *task=g_task_new(pending, NULL, NULL, NULL);
    if (error) g_task_return_error(task,error);
    else g_task_return_pointer(task,file,g_object_unref);
    callback(G_OBJECT(pending),G_ASYNC_RESULT(task),callback_data);
    g_object_unref(task);g_clear_object(&pending);
    while (g_main_context_iteration(NULL,FALSE));
}
static App start(void) {
    requests=sends=focus_changes=0;g_clear_pointer(&status,g_free);g_clear_pointer(&sent_root,g_free);
    App a={.shown=TRUE,.win=(GtkWindow *)0x1};return a;
}
static void selected_local(void) {
    App a=start();pi_connect_clicked(NULL,&a);
    g_assert_cmpuint(requests,==,1);g_assert_true(a.pi_selecting);
    g_assert_cmpint(focus_mode,==,GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
    pi_connect_clicked(NULL,&a);g_assert_cmpuint(requests,==,1);
    complete(g_file_new_for_path("/synthetic/prepared-owner"),NULL);
    g_assert_cmpuint(sends,==,1);g_assert_cmpstr(sent_root,==,"/synthetic/prepared-owner");
    g_assert_true(a.pi_optin);g_assert_false(a.pi_selecting);g_assert_null(a.picker_cancel);
    g_assert_nonnull(strstr(status,"fresh consent still required"));
    g_assert_cmpint(focus_mode,==,GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);
}
static void dismissed_or_error(void) {
    for (int i=0;i<3;i++) {
        App a=start();pi_connect_clicked(NULL,&a);
        complete(NULL,i==0?g_error_new_literal(GTK_DIALOG_ERROR,GTK_DIALOG_ERROR_DISMISSED,"private details"):
            i==1?g_error_new_literal(G_IO_ERROR,G_IO_ERROR_CANCELLED,"private details"):
            g_error_new_literal(G_IO_ERROR,G_IO_ERROR_FAILED,"private details"));
        g_assert_false(a.pi_optin);g_assert_cmpuint(sends,==,0);g_assert_null(a.picker_cancel);
        g_assert_nonnull(strstr(status,i<2?"cancelled":"chooser failed"));
        g_assert_null(strstr(status,"private details"));
        if (i==2) g_assert_cmpstr(a.pi_connect_error,==,status);
        else g_assert_null(a.pi_connect_error);
        g_free(a.pi_connect_error);
    }
}
static void stale_or_busy_or_dead(void) {
    for (int i=0;i<4;i++) {
        App a=start();pi_connect_clicked(NULL,&a);
        if (i==0) {a.shown=FALSE;a.win=NULL;}
        if (i==1) g_cancellable_cancel(a.picker_cancel);
        if (i==2) a.busy=TRUE;
        if (i==3) a.pi_dead=TRUE;
        complete(g_file_new_for_path("/synthetic/prepared-owner"),NULL);
        g_assert_cmpuint(sends,==,0);g_assert_false(a.pi_optin);
        g_assert_nonnull(strstr(status,"discarded"));g_assert_null(a.picker_cancel);
    }
}
static void remote_and_overlap(void) {
    App a=start();a.picker_cancel=g_cancellable_new();pi_connect_clicked(NULL,&a);
    g_assert_cmpuint(requests,==,0);g_assert_nonnull(strstr(status,"current picker"));
    g_clear_object(&a.picker_cancel);pi_connect_clicked(NULL,&a);
    complete(g_file_new_for_uri("sftp://example.invalid/private"),NULL);
    g_assert_false(a.pi_optin);g_assert_cmpuint(sends,==,0);
    g_assert_nonnull(strstr(status,"local prepared folder containing owner.json"));
    g_assert_cmpstr(a.pi_connect_error,==,status);g_free(a.pi_connect_error);
}
int main(int argc,char **argv) {
    g_test_init(&argc,&argv,NULL);
    g_test_add_func("/ui/pi-picker/local-unparented-focus",selected_local);
    g_test_add_func("/ui/pi-picker/cancel-error-visible",dismissed_or_error);
    g_test_add_func("/ui/pi-picker/stale-busy-dead",stale_or_busy_or_dead);
    g_test_add_func("/ui/pi-picker/remote-overlap",remote_and_overlap);
    int result=g_test_run();g_free(status);g_free(sent_root);return result;
}
