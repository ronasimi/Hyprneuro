/* Layer surfaces cannot be exported as portal xdg_toplevel parents. Keep this
 * chooser unparented, yield keyboard focus, and reject late/cancelled results. */
static void pi_picker_notice(App *a, const char *text, gboolean failed) {
    if (failed) {
        g_free(a->pi_connect_error); a->pi_connect_error = g_strdup(text);
        pi_route_update(a);
    }
    set_status(a, text);
}
static void pi_owner_selected(GObject *object, GAsyncResult *result, gpointer data) {
    g_autoptr(App) a = data;
    if (a->closing) {
        GError *error=NULL;
        GFile *file=gtk_file_dialog_select_folder_finish(GTK_FILE_DIALOG(object),result,&error);
        g_clear_object(&file); g_clear_error(&error);
        return;
    }
    gboolean accept = a->shown && a->pi_selecting && a->picker_cancel &&
        !g_cancellable_is_cancelled(a->picker_cancel) && !a->busy && !a->pi_optin && !a->pi_dead;
    a->pi_selecting = FALSE;
    g_clear_object(&a->picker_cancel);
    if (a->win) gtk_layer_set_keyboard_mode(a->win, GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);
    pi_route_update(a);
    GError *error = NULL;
    GFile *file = gtk_file_dialog_select_folder_finish(GTK_FILE_DIALOG(object), result, &error);
    if (!file) {
        gboolean cancelled = error && (g_error_matches(error, GTK_DIALOG_ERROR, GTK_DIALOG_ERROR_DISMISSED) ||
            g_error_matches(error, GTK_DIALOG_ERROR, GTK_DIALOG_ERROR_CANCELLED) ||
            g_error_matches(error, G_IO_ERROR, G_IO_ERROR_CANCELLED));
        pi_picker_notice(a, cancelled ? "Pi owner selection cancelled · no connection requested" :
            "Pi owner chooser failed · no connection requested; inspect portal before retry", !cancelled);
        g_clear_error(&error);
        return;
    }
    g_clear_error(&error);
    char *root = g_file_get_path(file);
    g_object_unref(file);
    if (!accept) set_status(a, "Pi owner selection discarded · hidden/cancelled/busy; no connection requested");
    else if (!root) pi_picker_notice(a, "Pi owner requires a local prepared folder containing owner.json; no connection requested", TRUE);
    else {
        g_clear_pointer(&a->pi_connect_error, g_free);
        a->pi_optin = TRUE; pi_render(a); /* explicit intent; never fallback on failure */
        set_status(a, "Pi owner selected · validating owner.json and connecting; fresh consent still required");
        if (!a->pi_process) pi_start(a); /* explicit chooser intent; host proof BEFORE child/Node */
        if (!a->pi_dead) pi_send(a, "connect", root, FALSE);
    }
    g_free(root);
}
static void pi_connect_clicked(GtkButton *button, gpointer data) {
    (void)button; App *a = data;
    if (a->busy) { set_status(a, "Cancel/settle current chat before changing mode; no replay"); return; }
    if (a->pi_optin) { pi_send(a, "disconnect", NULL, FALSE); return; }
    if (a->pi_selecting) return;
    if (a->picker_cancel) { set_status(a, "Finish or cancel the current picker before selecting a Pi owner"); return; }
    g_clear_pointer(&a->pi_connect_error, g_free);
    a->pi_selecting = TRUE; a->picker_cancel = g_cancellable_new(); pi_route_update(a);
    GtkFileDialog *dialog = gtk_file_dialog_new();
    gtk_file_dialog_set_title(dialog, "Select prepared private Pi owner root — not personal files");
    if (a->win) gtk_layer_set_keyboard_mode(a->win, GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
    gtk_file_dialog_select_folder(dialog, NULL, a->picker_cancel, pi_owner_selected, app_ref(a));
    g_object_unref(dialog);
}
