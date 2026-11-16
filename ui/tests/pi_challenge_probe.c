/* Private actual GTK/fixed-launch probe. Link wrappers serve ONLY owned synthetic
 * sidecar unit metadata; never query/start/change production systemd units. */
#define main hyprneuro_ui_main
#include "../src/hyprneuro.c"
#undef main
GDBusConnection *__wrap_g_bus_get_sync(GBusType type,GCancellable *cancel,GError **error) {
    (void)type;(void)cancel;(void)error;
    return (GDBusConnection *)g_object_new(G_TYPE_OBJECT,NULL);
}
GVariant *__wrap_g_dbus_connection_call_sync(GDBusConnection *bus,const gchar *name,const gchar *path,
 const gchar *interface,const gchar *method,GVariant *parameters,const GVariantType *reply_type,
 GDBusCallFlags flags,gint timeout,GCancellable *cancel,GError **error) {
    (void)bus;(void)name;(void)path;(void)interface;(void)parameters;(void)reply_type;
    (void)flags;(void)timeout;(void)cancel;(void)error;
    if (!strcmp(method,"GetUnit"))return g_variant_ref_sink(g_variant_new("(o)","/private/unit"));
    if (!strcmp(method,"GetAll")) {
        GVariantBuilder b;g_variant_builder_init(&b,G_VARIANT_TYPE("a{sv}"));
        g_variant_builder_add(&b,"{sv}","ActiveState",g_variant_new_string("active"));
        g_variant_builder_add(&b,"{sv}","SubState",g_variant_new_string("running"));
        g_variant_builder_add(&b,"{sv}","Job",g_variant_new("(uo)",0,"/"));
        return g_variant_ref_sink(g_variant_new("(a{sv})",&b));
    }
    g_assert_cmpstr(method,==,"Get");
    return g_variant_ref_sink(g_variant_new("(v)",g_variant_new_uint32((guint)g_ascii_strtoull(g_getenv("HN_FIXTURE_BROKER_PID"),NULL,10))));
}
int main(void) {
    gtk_init();const char *stage=NULL,*category=NULL;char *start=NULL;
    GSubprocess *child=pi_fixed_bridge(&stage,&category,&start);
    if (child) {
        /* Only this fixture's fixed child; bounded by parent watchdog. */
        g_subprocess_wait(child,NULL,NULL);g_object_unref(child);
        g_print("{\"result\":\"spawned\"}\n");
    } else {
        /* Real GtkLabel/accessible name contains exactly the production text. */
        char *status=pi_diagnostic_status(stage,category);
        GtkWidget *label=gtk_label_new(status);g_object_ref_sink(label);
        gtk_accessible_update_property(GTK_ACCESSIBLE(label),GTK_ACCESSIBLE_PROPERTY_DESCRIPTION,"hyprneuro-bootstrap-status",-1);
        g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(label)),==,status);
        pi_diagnostic_emit(stage,category,0);
        g_print("{\"result\":\"failed\",\"stage\":\"%s\",\"category\":\"%s\"}\n",pi_diagnostic_stage(stage),pi_diagnostic_category(category));
        GtkWidget *window=gtk_window_new();gtk_window_set_child(GTK_WINDOW(window),label);gtk_window_present(GTK_WINDOW(window));
        fflush(stdout);
        const char *ack=g_getenv("HN_FIXTURE_CAPTURE_ACK");gint64 end=g_get_monotonic_time()+3000000;
        while(ack && !g_file_test(ack,G_FILE_TEST_EXISTS) && g_get_monotonic_time()<end) {
            g_main_context_iteration(NULL,FALSE);g_usleep(1000);
        }
        gtk_window_destroy(GTK_WINDOW(window));g_object_unref(label);g_free(status);
    }
    g_free(start);return 0;
}
