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
