/* Private Xvfb adapter ONLY: compile the actual unchanged product construction
 * and callbacks, adapting only Wayland layer placement/focus to the private X11 surface.
 * No production binary/unit is modified. All sockets belong to private fixture. */
#define main hyprneuro_private_fixture_main
#include "../src/hyprneuro.c"
#undef main
#include <gdk/x11/gdkx.h>
#include <X11/Xlib.h>
void __wrap_gtk_layer_init_for_window(GtkWindow *w) {(void)w;}
void __wrap_gtk_layer_set_namespace(GtkWindow *w,const char *n) {(void)w;(void)n;}
void __wrap_gtk_layer_set_layer(GtkWindow *w,GtkLayerShellLayer l) {(void)w;(void)l;}
void __wrap_gtk_layer_set_exclusive_zone(GtkWindow *w,int v) {(void)w;(void)v;}
void __wrap_gtk_layer_set_anchor(GtkWindow *w,GtkLayerShellEdge e,gboolean v) {(void)w;(void)e;(void)v;}
void __wrap_gtk_layer_set_margin(GtkWindow *w,GtkLayerShellEdge e,int v) {(void)w;(void)e;(void)v;}
void __wrap_gtk_layer_set_keyboard_mode(GtkWindow *w,GtkLayerShellKeyboardMode m) {
    (void)m;
    GdkSurface *s=gtk_native_get_surface(GTK_NATIVE(w));
    if (s && gdk_surface_get_mapped(s)) {
        Display *d=gdk_x11_display_get_xdisplay(gdk_surface_get_display(s));
        XSetInputFocus(d,gdk_x11_surface_get_xid(s),RevertToParent,CurrentTime);XFlush(d);
    }
}
int main(int argc,char **argv) {return hyprneuro_private_fixture_main(argc,argv);}
/* Synthetic private systemd metadata ONLY for real trusted-launch fixture.
 * All non-systemd calls go to the real private session bus. */
GVariant *__real_g_dbus_connection_call_sync(GDBusConnection *,const gchar *,const gchar *,const gchar *,const gchar *,GVariant *,const GVariantType *,GDBusCallFlags,gint,GCancellable *,GError **);
GVariant *__wrap_g_dbus_connection_call_sync(GDBusConnection *bus,const gchar *name,const gchar *path,const gchar *iface,const gchar *method,GVariant *params,const GVariantType *type,GDBusCallFlags flags,gint timeout,GCancellable *cancel,GError **error) {
    const char *broker=g_getenv("HN_PRIVATE_BROKER_PID");
    if (broker && !g_strcmp0(name,"org.freedesktop.systemd1")) {
        g_printerr("PRIVATE SYNTHETIC UNIT method=%s\n",method);
        if (!g_strcmp0(method,"GetUnit")) return g_variant_ref_sink(g_variant_new("(o)","/fixture/sidecar"));
        if (!g_strcmp0(method,"GetAll")) {
            GVariantBuilder b;g_variant_builder_init(&b,G_VARIANT_TYPE("a{sv}"));
            g_variant_builder_add(&b,"{sv}","ActiveState",g_variant_new_string("active"));
            g_variant_builder_add(&b,"{sv}","SubState",g_variant_new_string("running"));
            g_variant_builder_add(&b,"{sv}","Job",g_variant_new("(uo)",0,"/"));
            return g_variant_ref_sink(g_variant_new("(a{sv})",&b));
        }
        if (!g_strcmp0(method,"Get"))return g_variant_ref_sink(g_variant_new("(v)",g_variant_new_uint32((guint)(g_getenv("HN_PRIVATE_WRONG_PEER")?getpid():g_ascii_strtoull(broker,NULL,10)))));
        g_error("Unexpected private metadata call");
    }
    return __real_g_dbus_connection_call_sync(bus,name,path,iface,method,params,type,flags,timeout,cancel,error);
}
GSubprocessLauncher *__real_g_subprocess_launcher_new(GSubprocessFlags);
GSubprocessLauncher *__wrap_g_subprocess_launcher_new(GSubprocessFlags flags) {
    if (g_getenv("HN_PRIVATE_BROKER_PID")) {
        g_printerr("PRIVATE BOOTSTRAP reached fixed child spawn; stderr=%s\n",g_getenv("HN_KEEP_PRODUCTION_STDERR") ? "production-silenced" : "fixture-inherited");
        if (!g_getenv("HN_KEEP_PRODUCTION_STDERR")) flags &= ~G_SUBPROCESS_FLAGS_STDERR_SILENCE;
    }
    return __real_g_subprocess_launcher_new(flags);
}
