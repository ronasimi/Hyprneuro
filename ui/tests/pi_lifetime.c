/* Actual callback/buffer ownership through cancellation after main unref.
 * No display, chooser, service, Node, network or human approval. */
#define main hyprneuro_ui_main
#include "../src/hyprneuro.c"
#undef main
static void late_read(void) {
    App *a=g_new0(App,1);a->references=1;
    a->pi_in=g_memory_input_stream_new_from_data("{}\n",3,NULL);
    GInputStream *stream=a->pi_in;
    a->pi_io=g_cancellable_new();
    pi_read_next(a);
    g_assert_cmpint(a->references,==,2);
    a->closing=TRUE;g_cancellable_cancel(a->pi_io);
    app_unref(a); /* callback still owns App AND read destination buffer */
    while (g_main_context_iteration(NULL,FALSE));
    g_object_unref(stream);
}
static void confirmed_reset(void) {
    App *a=g_new0(App,1);a->references=1;
    a->pi_child_exited=TRUE;
    pi_runtime_maybe_reset(a);g_assert_true(a->pi_child_exited); /* no receipt */
    a->pi_clean_disconnect=TRUE;a->pi_active_io=1;
    pi_runtime_maybe_reset(a);g_assert_true(a->pi_child_exited); /* callback pending */
    a->pi_active_io=0;
    pi_runtime_maybe_reset(a);
    g_assert_false(a->pi_child_exited);g_assert_false(a->pi_clean_disconnect);
    g_assert_null(a->pi_process);app_unref(a);
}
static void finite_clock(void) {
    App *a=g_new0(App,1);a->references=1;
    a->pi_deadline_ns=pi_boottime_ns()+7200000000000ULL;
    g_assert_true(pi_lifetime_tick(a));g_assert_false(a->pi_expiry_warned);
    a->closing=TRUE;g_assert_false(pi_lifetime_tick(a));
    app_unref(a);
}
int main(int argc,char **argv) {
    g_test_init(&argc,&argv,NULL);g_test_add_func("/pi/lifetime/late-read",late_read);
    g_test_add_func("/pi/lifetime/confirmed-reap-reset",confirmed_reset);
    g_test_add_func("/pi/lifetime/finite-boottime-presentation",finite_clock);
    return g_test_run();
}
