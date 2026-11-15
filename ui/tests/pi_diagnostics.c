/* Actual production decoder; no GUI, service, permission or model operations. */
#define main hyprneuro_ui_main
#include "../src/hyprneuro.c"
#undef main
static void decode(void) {
 const char *cases[]={"null","[]","{}","{\"type\":\"bootstrap_failure\",\"stage\":\"SECRET_NONCE\",\"category\":\"failure\"}","{\"type\":\"bootstrap_failure\",\"stage\":\"managed-import\",\"category\":\"SECRET\"}","{\"type\":\"ready\",\"stage\":\"managed-import\",\"category\":\"failure\"}","{\"type\":\"bootstrap_failure\",\"stage\":\"policy-read\",\"category\":\"failure\"}"};
 for(guint i=0;i<G_N_ELEMENTS(cases);i++){JsonParser*p=json_parser_new();g_assert_true(json_parser_load_from_data(p,cases[i],-1,NULL));g_assert_cmpstr(pi_diagnostic_frame_stage(json_parser_get_root(p)),==,"unknown");g_object_unref(p);}
 for(int n=0;n<1000;n++){char *text=g_strnfill(n,'x');JsonBuilder*b=json_builder_new();json_builder_begin_object(b);json_builder_set_member_name(b,"type");json_builder_add_string_value(b,"bootstrap_failure");json_builder_set_member_name(b,"stage");json_builder_add_string_value(b,text);json_builder_set_member_name(b,"category");json_builder_add_string_value(b,"failure");json_builder_end_object(b);JsonNode*o=json_builder_get_root(b);g_assert_cmpstr(pi_diagnostic_frame_stage(o),==,"unknown");json_node_unref(o);g_object_unref(b);g_free(text);}
 char invalid[]={ (char)0xff,0 };g_assert_cmpstr(pi_diagnostic_stage(invalid),==,"unknown");
 char *oversize=g_strnfill(PI_FRAME_MAX+1,'x');g_assert_cmpstr(pi_diagnostic_stage(oversize),==,"unknown");g_free(oversize);
 const char *ok="{\"type\":\"bootstrap_failure\",\"stage\":\"managed-import\",\"category\":\"failure\"}";JsonParser*p=json_parser_new();g_assert_true(json_parser_load_from_data(p,ok,-1,NULL));g_assert_cmpstr(pi_diagnostic_frame_stage(json_parser_get_root(p)),==,"managed-import");g_object_unref(p);
}
static void cap(void) {
 pi_diagnostic_count=0;
 for(int i=0;i<100;i++)pi_diagnostic_emit("SECRET_NONCE","SECRET_TOKEN",0);
 g_assert_cmpuint(pi_diagnostic_count,==,16);
}
static void child_exit(void) {
 for(int signal=0;signal<2;signal++) {
  pi_diagnostic_count=0;
  GSubprocess*p=g_subprocess_new(G_SUBPROCESS_FLAGS_NONE,NULL,"/bin/sh","-c",signal?"kill -TERM $$":"exit 7",NULL);
  g_assert_nonnull(p);const char*id=g_subprocess_get_identifier(p);char*start=pi_start_ticks((guint)g_ascii_strtoull(id,NULL,10));
  g_assert_nonnull(start);g_subprocess_wait_async(p,NULL,pi_owned_exit,start);
  gint64 end=g_get_monotonic_time()+2000000;
  while(!pi_diagnostic_count && g_get_monotonic_time()<end){g_main_context_iteration(NULL,FALSE);g_usleep(1000);}
  g_assert_cmpuint(pi_diagnostic_count,==,1);
  if(signal)g_assert_cmpint(g_subprocess_get_term_sig(p),==,SIGTERM);else g_assert_cmpint(g_subprocess_get_exit_status(p),==,7);
  g_object_unref(p);
 }
}
int main(int argc,char**argv){g_test_init(&argc,&argv,NULL);g_test_add_func("/pi/diagnostic-decoder",decode);g_test_add_func("/pi/diagnostic-cap",cap);g_test_add_func("/pi/owned-exit",child_exit);return g_test_run();}
