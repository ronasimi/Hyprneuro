/* ACTUAL GTK/fixed production bridge + synthetic fixture consent packets.
 * No automation of a genuine chooser or security Allow button. The only shim
 * maps the built-in broker UNIT NAME to one owned private cohort; all returned
 * manager state/PID metadata are REAL. Observer metadata is entirely unwrapped.
 */
#define main hyprneuro_ui_main
#include "../src/hyprneuro.c"
#undef main
/* Real D-Bus, only the closed private UNIT NAME differs from production.
 * Async connection has a 1000ms cancellation budget; every method retains the
 * production timeout/cancellable. No subprocess, fabricated state or PID. */
extern GVariant *__real_g_dbus_connection_call_sync(GDBusConnection *,const gchar *,const gchar *,const gchar *,const gchar *,GVariant *,const GVariantType *,GDBusCallFlags,gint,GCancellable *,GError **);
typedef struct { GMainLoop *loop;GDBusConnection *bus;GError *error; } FixtureBus;
static void fixture_bus_done(GObject *object,GAsyncResult *result,gpointer data) {
    (void)object;FixtureBus *state=data;
    state->bus=g_dbus_connection_new_for_address_finish(result,&state->error);g_main_loop_quit(state->loop);
}
static gboolean fixture_bus_timeout(gpointer data) {g_cancellable_cancel(data);return G_SOURCE_REMOVE;}
GDBusConnection *__wrap_g_bus_get_sync(GBusType type,GCancellable *c,GError **error) {
    if(type!=G_BUS_TYPE_SESSION || (c && g_cancellable_is_cancelled(c)))return NULL;
    FixtureBus state={.loop=g_main_loop_new(NULL,FALSE)};GCancellable *budget=g_cancellable_new();
    char *address=g_strdup_printf("unix:path=/run/user/%u/bus",(guint)geteuid());
    guint timer=g_timeout_add(1000,fixture_bus_timeout,budget);
    g_dbus_connection_new_for_address(address,G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT|G_DBUS_CONNECTION_FLAGS_MESSAGE_BUS_CONNECTION,NULL,budget,fixture_bus_done,&state);
    g_main_loop_run(state.loop);
    if(!g_cancellable_is_cancelled(budget))g_source_remove(timer);
    if(state.error){if(error)*error=state.error;else g_error_free(state.error);}
    g_object_unref(budget);g_main_loop_unref(state.loop);g_free(address);return state.bus;
}
GVariant *__wrap_g_dbus_connection_call_sync(GDBusConnection *b,const gchar *n,const gchar *p,
 const gchar *i,const gchar *method,GVariant *parameters,const GVariantType *t,GDBusCallFlags f,
 gint timeout,GCancellable *cancel,GError **error) {
    if(!strcmp(method,"GetUnit")) {
        const char *original=NULL;g_variant_get(parameters,"(&s)",&original);
        const char *unit=g_getenv("HN_FIXTURE_BROKER_UNIT");
        if(g_strcmp0(original,"hyprneuro.service") || !unit || !g_str_has_prefix(unit,"hyprneuro-test-boundary-"))return NULL;
        parameters=g_variant_new("(s)",unit);
    }
    return __real_g_dbus_connection_call_sync(b,n,p,i,method,parameters,t,f,MIN(timeout>0?timeout:1000,1000),cancel,error);
}
static int fixture_manager_probe(void) {
    GError *error=NULL;GDBusConnection *bus=__wrap_g_bus_get_sync(G_BUS_TYPE_SESSION,NULL,&error);
    if(!bus){g_printerr("NONAUTHORITATIVE manager-probe stage=connect result=reject\n");g_clear_error(&error);return 3;}
    GVariant *unit=__wrap_g_dbus_connection_call_sync(bus,"org.freedesktop.systemd1","/org/freedesktop/systemd1","org.freedesktop.systemd1.Manager","GetUnit",g_variant_new("(s)","hyprneuro.service"),G_VARIANT_TYPE("(o)"),0,1000,NULL,&error);
    if(!unit){g_printerr("NONAUTHORITATIVE manager-probe stage=get-unit result=reject\n");g_clear_error(&error);g_object_unref(bus);return 3;}
    const char *path;g_variant_get(unit,"(&o)",&path);
    GVariant *state=__wrap_g_dbus_connection_call_sync(bus,"org.freedesktop.systemd1",path,"org.freedesktop.DBus.Properties","GetAll",g_variant_new("(s)","org.freedesktop.systemd1.Unit"),G_VARIANT_TYPE("(a{sv})"),0,1000,NULL,&error);
    GVariant *pid=state?__wrap_g_dbus_connection_call_sync(bus,"org.freedesktop.systemd1",path,"org.freedesktop.DBus.Properties","Get",g_variant_new("(ss)","org.freedesktop.systemd1.Service","MainPID"),G_VARIANT_TYPE("(v)"),0,1000,NULL,&error):NULL;
    gboolean ok=state && pid;g_print("NONAUTHORITATIVE manager-probe actual-interfaces=o,a{sv},v result=%s\n",ok?"ok":"reject");
    if(state)g_variant_unref(state);if(pid)g_variant_unref(pid);g_variant_unref(unit);g_object_unref(bus);g_clear_error(&error);return ok?0:3;
}
static void send_fixture(GOutputStream *out,const char *op,const char *text,gboolean allowed) {
    char *frame=pi_encode_frame(op,text,allowed);gsize written=0;
    g_assert_true(g_output_stream_write_all(out,frame,strlen(frame),&written,NULL,NULL));
    g_assert_cmpuint(written,==,strlen(frame));g_free(frame);
}
int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--manager-query-only"))return fixture_manager_probe();
    gtk_init();const char *root=g_getenv("HN_FIXTURE_ROOT");g_assert_nonnull(root);
    GtkWidget *window=gtk_window_new();gtk_window_set_child(GTK_WINDOW(window),gtk_label_new("SYNTHETIC fixture packets — NOT human chooser/Allow acceptance"));gtk_window_present(GTK_WINDOW(window));
    while(g_main_context_iteration(NULL,FALSE));
    const char *stage=NULL,*category=NULL;char *start=NULL;
    GSubprocess *child=pi_fixed_bridge(&stage,&category,&start);
    if(!child){g_printerr("FIXTURE fixed bridge failed %s/%s\n",stage,category);return 2;}
    GOutputStream *out=g_subprocess_get_stdin_pipe(child);
    GDataInputStream *in=g_data_input_stream_new(g_subprocess_get_stdout_pipe(child));
    char *packets_path=g_build_filename(root,"gtk-packets.jsonl",NULL);FILE *packets=fopen(packets_path,"w");g_free(packets_path);g_assert_nonnull(packets);
    gboolean connected=FALSE,submitted=FALSE,settled=FALSE,disconnected=FALSE;guint consents=0;
    for(guint count=0;count<400 && !disconnected;count++) {
        gsize length=0;char *line=g_data_input_stream_read_line(in,&length,NULL,NULL);g_assert_nonnull(line);g_assert_cmpuint(length,<,PI_FRAME_MAX);
        fprintf(packets,"%s\n",line);fflush(packets);
        JsonParser *parser=json_parser_new();g_assert_true(json_parser_load_from_data(parser,line,length,NULL));g_free(line);
        JsonNode *packet=json_parser_get_root(parser);const char *type=jstr(jmember(packet,"type")),*op=jstr(jmember(packet,"op"));
        if(!g_strcmp0(type,"error") && g_getenv("HN_FIXTURE_BAD_ROOT")) {
            g_assert_cmpstr(op,==,"connect");
            g_assert_cmpstr(jstr(jmember(jmember(packet,"connect_diagnostic"),"site")),==,"owner-policy");
            g_object_unref(parser);g_output_stream_close(out,NULL,NULL);
            g_assert_true(g_subprocess_wait_check(child,NULL,NULL));
            char *done=g_build_filename(root,"gtk-sdk-complete",NULL);
            g_assert_true(g_file_set_contents(done,"NEGATIVE fixed-owner mismatch; no owner execution/authentication\n",-1,NULL));
            g_free(done);fclose(packets);g_object_unref(in);g_object_unref(child);g_free(start);gtk_window_destroy(GTK_WINDOW(window));return 0;
        }
        if(!g_strcmp0(type,"error") && !g_strcmp0(op,"disconnect") && g_getenv("HN_FIXTURE_UNKNOWN_CLEANUP")) {
            g_object_unref(parser);g_output_stream_close(out,NULL,NULL);
            g_assert_true(g_subprocess_wait_check(child,NULL,NULL));
            const char *retry_stage=NULL,*retry_category=NULL;char *retry_start=NULL;
            GSubprocess *retry=pi_fixed_bridge(&retry_stage,&retry_category,&retry_start);
            g_assert_null(retry);g_assert_null(retry_start); /* consumed cell, NO new child/helper */
            char *denied=g_build_filename(root,"reconnect-denied",NULL);
            g_assert_true(g_file_set_contents(denied,"UNKNOWN cleanup: fresh Connect denied\n",-1,NULL));g_free(denied);
            char *done=g_build_filename(root,"gtk-sdk-complete",NULL);
            g_assert_true(g_file_set_contents(done,"NEGATIVE lost/failed cleanup receipt retained UNKNOWN\n",-1,NULL));g_free(done);
            fclose(packets);g_object_unref(in);g_object_unref(child);g_free(start);gtk_window_destroy(GTK_WINDOW(window));return 0;
        }
        if(!g_strcmp0(type,"error") && g_getenv("HN_FIXTURE_PROOF_DENIAL")) {
            char *fault=g_build_filename(root,"fault-injected",NULL);g_assert_true(g_file_test(fault,G_FILE_TEST_EXISTS));g_free(fault);
            g_object_unref(parser);g_output_stream_close(out,NULL,NULL);
            g_assert_true(g_subprocess_wait(child,NULL,NULL));g_assert_true(g_subprocess_get_if_exited(child));
            int status=g_subprocess_get_exit_status(child);
            char *exit_path=g_build_filename(root,"negative-child-exit",NULL),*exit_text=g_strdup_printf("%d\n",status);
            g_assert_true(g_file_set_contents(exit_path,exit_text,-1,NULL));g_free(exit_path);g_free(exit_text);
            g_assert_cmpint(status,==,1); /* fail-closed teardown, NEVER a clean receipt */
            char *done=g_build_filename(root,"gtk-sdk-complete",NULL);
            g_assert_true(g_file_set_contents(done,"NEGATIVE actual-helper proof denied; child exit1/UNKNOWN\n",-1,NULL));g_free(done);
            fclose(packets);g_object_unref(in);g_object_unref(child);g_free(start);gtk_window_destroy(GTK_WINDOW(window));return 0;
        }
        g_assert_cmpstr(type,!=,"error");g_assert_cmpstr(type,!=,"unavailable");g_assert_cmpstr(type,!=,"bootstrap_failure");
        if(!g_strcmp0(type,"bridge_ready")) {
            char *ready=g_build_filename(root,"ui-child-host-proof.ready",NULL);g_assert_true(g_file_set_contents(ready,"NONAUTHORITATIVE fixture sequencing\n",-1,NULL));g_free(ready);
            const char *bad_root=g_getenv("HN_FIXTURE_BAD_ROOT");
            if(bad_root){send_fixture(out,"connect",bad_root,FALSE);g_object_unref(parser);continue;}
            char *socket=g_build_filename(root,"owner","owner.sock",NULL);gint64 end=g_get_monotonic_time()+10000000;
            while(!g_file_test(socket,G_FILE_TEST_EXISTS) && g_get_monotonic_time()<end){g_main_context_iteration(NULL,FALSE);g_usleep(10000);}
            g_assert_true(g_file_test(socket,G_FILE_TEST_EXISTS));g_free(socket);
            char *owner=g_build_filename(root,"owner",NULL);send_fixture(out,"connect",owner,FALSE);g_free(owner);
        } else if(!g_strcmp0(type,"connected")) {connected=TRUE;submitted=TRUE;send_fixture(out,"chat","SYNTHETIC_GTK_SDK_READ_FIXTURE",FALSE);}
        else if(!g_strcmp0(type,"host_event")) {
            JsonNode *event=jmember(packet,"event");
            if(!g_strcmp0(jstr(jmember(event,"type")),"consent")) {
                const char *kind=jstr(jmember(jmember(event,"audit"),"kind"));
                g_assert_true(!g_strcmp0(kind,"grant_create") || !g_strcmp0(kind,"read_decision"));
                g_assert_cmpuint(++consents,<=,2);
                /* Explicit synthetic packet, NOT a Gtk security-button action. */
                send_fixture(out,"consent",jstr(jmember(event,"id")),!g_strcmp0(kind,"grant_create") || g_strcmp0(g_getenv("HN_FIXTURE_DENY_READ"),"1"));
            }
        } else if(!g_strcmp0(type,"result") && !g_strcmp0(op,"chat")) {settled=TRUE;send_fixture(out,"disconnect",NULL,FALSE);}
        else if(!g_strcmp0(type,"disconnected")) disconnected=TRUE;
        g_object_unref(parser);while(g_main_context_iteration(NULL,FALSE));
    }
    fclose(packets);g_assert_true(connected && submitted && settled && disconnected);g_assert_cmpuint(consents,==,2);
    g_output_stream_close(out,NULL,NULL);g_assert_true(g_subprocess_wait_check(child,NULL,NULL));
    char *done=g_build_filename(root,"gtk-sdk-complete",NULL);g_assert_true(g_file_set_contents(done,"SYNTHETIC fixture; cleanup receipt and exact child exit confirmed\n",-1,NULL));g_free(done);
    gtk_window_destroy(GTK_WINDOW(window));g_object_unref(in);g_object_unref(child);g_free(start);return 0;
}
