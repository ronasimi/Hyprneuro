/* Private inherited pipes to the asynchronous established-client adapter.
 * No credential handling, owner creation, lifecycle or text-as-command parsing
 * occurs on this path. All callbacks below execute on GTK's main context. */
#define PI_FRAME_MAX 65536

static const char *pi_observed_state(JsonNode *status) {
    const char *state = jstr(jmember(status, "state"));
    const char *phase = jstr(jmember(status, "owner_phase"));
    if (!g_strcmp0(phase, "failed") || !g_strcmp0(state, "failed")) return "failed";
    if (!g_strcmp0(phase, "transition") || !g_strcmp0(state, "transition")) return "transition";
    if (!g_strcmp0(state, "on")) return !g_strcmp0(phase, "hermes") ? "on" : "failed";
    if (!g_strcmp0(state, "off")) return !g_strcmp0(phase, "ordinary") ? "off" : "failed";
    return "unavailable";
}

/* Explicit authenticated owner mode, never infer ordinary safety from an
 * unavailable lifecycle alone. Failed/transition/malformed status stays closed. */
static gboolean pi_normal_only_ready(JsonNode *status) {
    JsonNode *mode = jmember(status, "normal_only");
    return mode && JSON_NODE_HOLDS_VALUE(mode) && json_node_get_value_type(mode) == G_TYPE_BOOLEAN &&
        json_node_get_boolean(mode) && !g_strcmp0(jstr(jmember(status, "state")), "unavailable") &&
        !g_strcmp0(jstr(jmember(status, "owner_phase")), "ordinary");
}

static gboolean pi_parent_only_ready(JsonNode *status) {
    JsonNode *mode=jmember(status,"parent_only"), *tools=jmember(status,"tools");
    return pi_normal_only_ready(status) && mode && JSON_NODE_HOLDS_VALUE(mode) &&
        json_node_get_value_type(mode)==G_TYPE_BOOLEAN && json_node_get_boolean(mode) &&
        tools && JSON_NODE_HOLDS_ARRAY(tools) && json_array_get_length(json_node_get_array(tools))==1 &&
        !g_strcmp0(jstr(json_array_get_element(json_node_get_array(tools),0)),"read");
}

static gboolean pi_route_allowed(App *a, gboolean native) {
    if (!a->pi_optin) return TRUE;
    if (!a->pi_connected) return FALSE;
    if (a->pi_normal_only && !a->pi_transition && !g_strcmp0(a->pi_state, "unavailable")) return TRUE;
    if (native) return !g_strcmp0(a->pi_state, "off") || !g_strcmp0(a->pi_state, "on") ||
        !g_strcmp0(a->pi_state, "transition");
    return !a->pi_transition && !g_strcmp0(a->pi_state, "off");
}
static void pi_route_update(App *a) {
    if (!a->pi_route) return;
    if (a->pi_connect) {
        gtk_button_set_label(GTK_BUTTON(a->pi_connect), a->pi_optin ? "Disconnect Pi → Legacy" : "Connect Pi owner…");
        gtk_widget_set_sensitive(a->pi_connect, !a->pi_dead && !a->pi_selecting);
    }
    if (a->pi_row) gtk_widget_set_visible(a->pi_row, a->pi_optin);
    if (!a->pi_optin) {
        gtk_label_set_text(GTK_LABEL(a->pi_route), a->pi_connect_error ? a->pi_connect_error :
            "Legacy sidecar · tool-free chat/media · Pi disconnected");
        return;
    }
    if (!a->pi_connected) {
        gtk_label_set_text(GTK_LABEL(a->pi_route), a->pi_connect_error ? a->pi_connect_error :
            "Pi disconnected/connecting · no tools available · no fallback; Disconnect returns to Legacy");
        return;
    }
    gtk_label_set_text(GTK_LABEL(a->pi_route), a->attachment_b64 ?
        "Attachment → legacy sidecar · NO Pi tools/history · requires ordinary owner" :
        a->pi_parent_only ? "Pi parent READONLY · no children/network/shell/desktop · fresh consent per read" :
        "Text → Pi owner · native tools require fresh host consent");
}

static gboolean pi_cancelled_result(JsonNode *result) {
    JsonNode *settled = jmember(result, "settled"), *cancelled = jmember(result, "cancelled");
    return jboolean(cancelled) && json_node_get_boolean(cancelled) &&
        jboolean(settled) && !json_node_get_boolean(settled) &&
        !g_strcmp0(jstr(jmember(result, "outcome")), "cancelled-known");
}

static void pi_finish_chat(App *a, gboolean success, const char *error) {
    if (!a->busy || !a->pi_chat) return;
    ChatDoneData *d = g_new0(ChatDoneData, 1);
    d->app = a; d->success = success && !a->pi_native_error;
    d->error = g_strdup(error ? error : "Native turn failed/aborted; inspect Pi session");
    on_chat_done(d);
}

static void pi_finish_cancelled(App *a) {
    if (!a->busy || !a->pi_chat) return;
    ChatDoneData *d = g_new0(ChatDoneData, 1);
    d->app = a; d->cancelled = TRUE; /* Not inference success or failure. */
    on_chat_done(d);
}

static void pi_close_dialog(App *a) {
    if (a->pi_dialog) gtk_window_destroy(a->pi_dialog);
    a->pi_dialog = NULL;
    g_clear_pointer(&a->pi_consent_id, g_free);
}

static void pi_render(App *a) {
    gboolean on = !g_strcmp0(a->pi_state, "on");
    a->pi_rendering = TRUE;
    gtk_switch_set_active(a->pi_switch, on);
    gtk_switch_set_state(a->pi_switch, on);
    a->pi_rendering = FALSE;
    gtk_widget_set_sensitive(GTK_WIDGET(a->pi_switch), a->pi_connected &&
        !a->pi_transition && (!g_strcmp0(a->pi_state, "off") || on));
    char *label = g_strdup_printf("MoE · %s%s", a->pi_state,
        a->pi_transition ? " · transition request pending" : a->pi_parent_only ? " · normal-only · read only · no helpers" : a->pi_normal_only ? " · normal-only" : "");
    gtk_label_set_text(GTK_LABEL(a->pi_label), label);
    gtk_accessible_update_property(GTK_ACCESSIBLE(a->pi_switch),
        GTK_ACCESSIBLE_PROPERTY_DESCRIPTION, label, -1);
    g_free(label);
    pi_route_update(a);
}

static void pi_owner_unavailable(App *a) {
    g_free(a->pi_connect_error);
    a->pi_connect_error = g_strdup("Pi disconnected/unavailable · no tools or fallback; inspect checkpoint before reconnect");
    a->pi_parent_only = FALSE; a->pi_normal_only = FALSE; a->pi_connected = FALSE; a->pi_transition = FALSE;
    a->pi_on_pending = a->pi_off_pending = FALSE;
    g_free(a->pi_state); a->pi_state = g_strdup("unavailable");
    pi_close_dialog(a); pi_render(a);
    pi_finish_chat(a, FALSE, "Pi disconnected/unavailable; outcome may be unknown. No retry/fallback.");
}
static void pi_unavailable(App *a) {
    if (a->pi_dead) return;
    a->pi_dead = TRUE;
    if (a->pi_io) g_cancellable_cancel(a->pi_io);
    pi_owner_unavailable(a);
    if (a->pi_out) g_output_stream_close(a->pi_out, NULL, NULL);
}

/* Diagnostics are never readiness, consent or authority. GTK main-context only. */
static guint pi_diagnostic_count;
static const char *pi_diagnostic_category(const char *category) {
    const char *known[]={"failure","exit","signal","unknown","timeout","identity","eof","framing","json","schema","io",NULL};
    for (int i=0;known[i];i++)if (!g_strcmp0(category,known[i]))return known[i];
    return "unknown";
}
static const char *pi_diagnostic_stage(const char *stage) {
    const char *known[]={"policy-read","policy-hash","policy-schema","entry-read","entry-hash",
        "broker-connect","broker-peer","sidecar-identity","challenge","spawn","child-start","attest-write",
        "broker-peer-check","broker-peer-uid","broker-ui-identity","broker-unit-command","broker-unit-metadata","broker-unit-state","broker-unit-job","broker-unit-pid","broker-ui-process","broker-ui-peer-pid","broker-ui-uid","broker-ui-cgroup","broker-ui-exe-hash","broker-launch-frame","broker-child-identity","broker-launch-ready","broker-private-operation","broker-unknown","broker-inherited","stdio-setup","managed-import","managed-init","bridge-eof","child-exit",NULL};
    if (stage && strlen(stage)<=32 && g_utf8_validate(stage,-1,NULL))
        for (int i=0;known[i];i++)if (!strcmp(stage,known[i]))return known[i];
    return "unknown";
}
static void pi_diagnostic_emit(const char *stage,const char *category,int status) {
    if (pi_diagnostic_count>=16)return;
    pi_diagnostic_count++;
    category=pi_diagnostic_category(category);
    g_printerr("{\"diagnostic\":\"NONAUTHORITATIVE\",\"stage\":\"%s\",\"category\":\"%s\",\"status\":%d}\n",
        pi_diagnostic_stage(stage),category,status);
}
static const char *pi_diagnostic_frame_stage(JsonNode *packet) {
    if (!packet || !JSON_NODE_HOLDS_OBJECT(packet))return "unknown";
    JsonObject *o=json_node_get_object(packet);
    const char *stage=jstr(jmember(packet,"stage")), *category=jstr(jmember(packet,"category"));
    if (json_object_get_size(o)!=3 || g_strcmp0(jstr(jmember(packet,"type")),"bootstrap_failure") || g_strcmp0(category,"failure"))return "unknown";
    if (!g_strcmp0(stage,"broker-inherited") || !g_strcmp0(stage,"stdio-setup") || !g_strcmp0(stage,"managed-import") || !g_strcmp0(stage,"managed-init"))return pi_diagnostic_stage(stage);
    return "unknown";
}
static char *pi_diagnostic_status(const char *stage,const char *category) {
    return g_strdup_printf("Pi bridge unavailable · diagnostic %s/%s · no authority/retry",
        pi_diagnostic_stage(stage),pi_diagnostic_category(category));
}
static void pi_diagnostic_fail_category(App *a,const char *stage,const char *category) {
    pi_unavailable(a);
    g_free(a->pi_connect_error);
    a->pi_connect_error=pi_diagnostic_status(stage,category);
    pi_route_update(a);pi_diagnostic_emit(stage,category,0);
}
static void pi_diagnostic_fail(App *a,const char *stage) {
    pi_diagnostic_fail_category(a,stage,"failure");
}
static void pi_owned_exit(GObject *object,GAsyncResult *result,gpointer data) {
    GError *error=NULL;
    if (g_subprocess_wait_finish(G_SUBPROCESS(object),result,&error)) {
        if (g_subprocess_get_if_exited(G_SUBPROCESS(object)))pi_diagnostic_emit("child-exit","exit",g_subprocess_get_exit_status(G_SUBPROCESS(object)));
        else if (g_subprocess_get_if_signaled(G_SUBPROCESS(object)))pi_diagnostic_emit("child-exit","signal",g_subprocess_get_term_sig(G_SUBPROCESS(object)));
    } else pi_diagnostic_emit("child-exit","unknown",0);
    g_clear_error(&error);g_free(data); /* immutable pre-wait start, never App */
}

static void pi_write_next(App *a);
static void pi_written(GObject *object, GAsyncResult *result, gpointer data) {
    App *a = data;
    gboolean ok = g_output_stream_write_all_finish(G_OUTPUT_STREAM(object), result, NULL, NULL);
    g_bytes_unref(g_queue_pop_head(&a->pi_writes));
    a->pi_writing = FALSE;
    if (!ok) pi_unavailable(a);
    if (a->pi_dead) {
        /* close() during an outstanding write may return PENDING. Now the
         * write has settled, guarantee EOF so the adapter drops control auth. */
        g_output_stream_close(a->pi_out, NULL, NULL);
        g_queue_clear_full(&a->pi_writes, (GDestroyNotify)g_bytes_unref);
        return;
    }
    pi_write_next(a);
}
static void pi_write_next(App *a) {
    if (a->pi_writing || g_queue_is_empty(&a->pi_writes) || a->pi_dead || !a->pi_out) return;
    GBytes *bytes = g_queue_peek_head(&a->pi_writes);
    gsize size; const void *data = g_bytes_get_data(bytes, &size);
    a->pi_writing = TRUE;
    g_output_stream_write_all_async(a->pi_out, data, size, G_PRIORITY_DEFAULT,
        a->pi_io, pi_written, a);
}
/* The pipe frame uses this same encoder for preflight and submission. */
static char *pi_encode_frame(const char *op, const char *text, gboolean allowed) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "op"); json_builder_add_string_value(b, op);
    if (text) {
        json_builder_set_member_name(b, !strcmp(op, "consent") ? "answer_id" : !strcmp(op, "connect") ? "root" : "text");
        json_builder_add_string_value(b, text);
    }
    if (!strcmp(op, "consent")) {
        json_builder_set_member_name(b, "allowed"); json_builder_add_boolean_value(b, allowed);
    }
    json_builder_end_object(b);
    JsonNode *root = json_builder_get_root(b);
    JsonGenerator *g = json_generator_new(); json_generator_set_root(g, root);
    char *json = json_generator_to_data(g, NULL);
    char *line = g_strconcat(json, "\n", NULL);
    g_free(json); json_node_unref(root); g_object_unref(g); g_object_unref(b);
    return line;
}

/* Match Python ensure_ascii=False/default separators and the owner's JS .length.
 * The owner envelope includes its fixed32-byte hex request ID and final newline.
 * Count JSON control/quote/backslash escapes, not just raw UTF-8 text bytes. */
static gboolean pi_clear_valid_draft(GtkTextBuffer *composer, const char *text) {
    if (!g_utf8_validate(text, -1, NULL)) return FALSE;
    gsize bytes = sizeof("{\"op\": \"chat\", \"id\": \"00000000000000000000000000000000\", \"text\": \"\"}\n") - 1;
    guint units = 0;
    gboolean nonblank = FALSE;
    for (const char *p = text; *p; p = g_utf8_next_char(p)) {
        gunichar ch = g_utf8_get_char(p);
        units += ch > 0xffff ? 2 : 1;
        if (ch == '"' || ch == '\\' || ch == '\b' || ch == '\f' || ch == '\n' || ch == '\r' || ch == '\t')
            bytes += 2;
        else bytes += ch < 0x20 ? 6 : g_utf8_next_char(p) - p;
        if (units > 16000 || bytes > PI_FRAME_MAX) return FALSE;
        /* Reject Python-strip or ECMAScript-trim-only drafts before clearing. */
        if (!g_unichar_isspace(ch) && ch != 0xfeff && !(ch >= 0x1c && ch <= 0x1f)) nonblank = TRUE;
    }
    if (!nonblank) return FALSE;
    char *frame = pi_encode_frame("chat", text, FALSE);
    gboolean fits = strlen(frame) <= PI_FRAME_MAX;
    g_free(frame);
    if (fits) gtk_text_buffer_set_text(composer, "", -1);
    return fits;
}

static void pi_send(App *a, const char *op, const char *text, gboolean allowed) {
    gboolean mode = !strcmp(op, "connect") || !strcmp(op, "disconnect");
    if (a->pi_dead || !a->pi_out || (!a->pi_connected && !mode) || g_queue_get_length(&a->pi_writes) >= 8) {
        pi_unavailable(a); return;
    }
    char *line = pi_encode_frame(op, text, allowed);
    if (strlen(line) <= PI_FRAME_MAX) {
        g_queue_push_tail(&a->pi_writes, g_bytes_new_take(line, strlen(line)));
        pi_write_next(a);
    } else { g_free(line); pi_finish_chat(a, FALSE, "Pi frame exceeds bound; draft was not submitted"); }
}
static void pi_send_text(App *a, const char *text) { pi_send(a, "chat", text, FALSE); }

static void pi_control(App *a, const char *op) {
    if (!a->pi_connected) { set_status(a, "Pi unavailable · explicit opt-in and existing owner required"); return; }
    if (strcmp(op, "status") && a->pi_normal_only) { set_status(a, "Lifecycle unavailable · normal-only owner; text/read remains available"); return; }
    if (strcmp(op, "status") && a->busy && !a->pi_chat) {
        set_status(a, "Wait for legacy media/chat before changing residency"); return;
    }
    if (!strcmp(op, "on") && (a->pi_transition || g_strcmp0(a->pi_state, "off"))) {
        set_status(a, "MoE on refused · observed state not off"); return;
    }
    if (!strcmp(op, "off") && a->pi_off_pending) return;
    if (strcmp(op, "status")) {
        if (!strcmp(op, "on")) a->pi_on_pending = TRUE;
        else a->pi_off_pending = TRUE;
        a->pi_transition = TRUE; pi_render(a);
    }
    pi_send(a, op, NULL, FALSE);
}
static gboolean pi_switch_change(GtkSwitch *sw, gboolean state, gpointer data) {
    (void)sw; App *a = data;
    if (!a->pi_rendering) pi_control(a, state ? "on" : "off");
    return TRUE; /* Never optimistic: active/state are set by observed status. */
}
static void pi_cancel_chat(GtkButton *button, gpointer data) {
    (void)button; App *a = data;
    gtk_widget_set_sensitive(a->pi_cancel, FALSE);
    set_status(a, "Pi cancel requested · outcome may be unknown");
    pi_send(a, "cancel", NULL, FALSE);
}
static void pi_cancel_on(GtkButton *button, gpointer data) {
    (void)button; pi_control(data, "off");
}

/* Only the composer submission boundary calls this. No assistant/event text
 * reaches it. Exact typed user commands are controls, not native prompts. */
static const char *pi_command(const char *text) {
    if (!g_strcmp0(text, "/moe on")) return "on";
    if (!g_strcmp0(text, "/moe off")) return "off";
    if (!g_strcmp0(text, "/moe status")) return "status";
    return NULL;
}
static gboolean pi_typed_command(App *a) {
    /* Unit helper busy guard uses no display-backed input. */
    if (!a->input) return FALSE;
    GtkTextBuffer *buf = gtk_text_view_get_buffer(a->input);
    GtkTextIter s, e; gtk_text_buffer_get_bounds(buf, &s, &e);
    char *text = gtk_text_buffer_get_text(buf, &s, &e, FALSE);
    const char *op = pi_command(text);
    gboolean command = op || !strcmp(text, "/moe") || g_str_has_prefix(text, "/moe ");
    if (command) {
        if (op) { pi_control(a, op); gtk_text_buffer_set_text(buf, "", -1); }
        else set_status(a, "Use exact /moe on, /moe off, or /moe status");
    }
    g_free(text); return command;
}

static void pi_consent_answer(GtkButton *button, gpointer data) {
    App *a = data;
    gboolean allowed = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(button), "pi-allow"));
    if (a->pi_consent_id) pi_send(a, "consent", a->pi_consent_id, allowed);
    pi_close_dialog(a);
}
static gboolean pi_consent_close(GtkWindow *window, gpointer data) {
    (void)window; App *a = data;
    if (a->pi_consent_id) pi_send(a, "consent", a->pi_consent_id, FALSE);
    pi_close_dialog(a); return TRUE;
}
static gboolean pi_consent_key(GtkEventControllerKey *controller, guint key, guint code,
                                GdkModifierType state, gpointer data) {
    (void)controller; (void)code; (void)state;
    if (key != GDK_KEY_Escape) return FALSE;
    App *a = data; pi_consent_close(a->pi_dialog, a); return TRUE;
}
static void pi_consent(App *a, JsonNode *event) {
    const char *id = jstr(jmember(event, "id")), *title = jstr(jmember(event, "title"));
    const char *detail = jstr(jmember(event, "detail"));
    if (!id || !title || !detail || strlen(id)>80 || strlen(title)>1200 || strlen(detail)>96000) {
        pi_unavailable(a); return;
    }
    if (a->pi_consent_id || !a->shown) { pi_send(a, "consent", id, FALSE); return; }
    a->pi_consent_id = g_strdup(id);
    a->pi_dialog = GTK_WINDOW(gtk_window_new());
    gtk_window_set_title(a->pi_dialog, "Pi host consent · fresh human decision");
    gtk_window_set_transient_for(a->pi_dialog, a->win);
    /* Non-modal: drafts/chat may be submitted while an on request waits. The
     * owner serializes it; a pending chat never allows a second chat submission. */
    gtk_window_set_default_size(a->pi_dialog, 560, 360);
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_window_set_child(a->pi_dialog, box);
    GtkWidget *heading = gtk_label_new(title);
    gtk_label_set_wrap(GTK_LABEL(heading), TRUE); gtk_box_append(GTK_BOX(box), heading);
    GtkWidget *warning = gtk_label_new("Host request, not model approval. Exact task/action details below. Deny is safe; Bash/command execution is UNSANDBOXED.");
    gtk_label_set_wrap(GTK_LABEL(warning), TRUE); gtk_box_append(GTK_BOX(box), warning);
    GtkWidget *scroll = gtk_scrolled_window_new(); gtk_widget_set_vexpand(scroll, TRUE);
    GtkWidget *view = gtk_text_view_new(); gtk_text_view_set_editable(GTK_TEXT_VIEW(view), FALSE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(view), GTK_WRAP_WORD_CHAR);
    gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(view)), detail, -1);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), view); gtk_box_append(GTK_BOX(box), scroll);
    GtkWidget *buttons = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_box_append(GTK_BOX(box), buttons);
    const char *names[] = {"Deny", "Allow exact action once"};
    for (int i=0; i<2; i++) {
        GtkWidget *b = gtk_button_new_with_label(names[i]);
        g_object_set_data(G_OBJECT(b), "pi-allow", GINT_TO_POINTER(i));
        g_signal_connect(b, "clicked", G_CALLBACK(pi_consent_answer), a);
        gtk_box_append(GTK_BOX(buttons), b);
        if (!i) gtk_window_set_default_widget(a->pi_dialog, b);
    }
    g_signal_connect(a->pi_dialog, "close-request", G_CALLBACK(pi_consent_close), a);
    GtkEventController *key = gtk_event_controller_key_new();
    g_signal_connect(key, "key-pressed", G_CALLBACK(pi_consent_key), a);
    gtk_widget_add_controller(GTK_WIDGET(a->pi_dialog), key);
    gtk_window_present(a->pi_dialog);
}

static void pi_packet(App *a, JsonNode *packet) {
    if (a->pi_dead) return; /* Late buffered status/events cannot resurrect a disconnect. */
    const char *type = jstr(jmember(packet, "type"));
    const char *op = jstr(jmember(packet, "op"));
    if (!g_strcmp0(type,"bootstrap_failure")) {
        pi_diagnostic_fail(a,pi_diagnostic_frame_stage(packet));
        return; /* NEVER any ready/consent interpretation */
    }
    if (!g_strcmp0(type, "disconnected")) {
        pi_owner_unavailable(a); a->pi_optin = FALSE;
        g_clear_pointer(&a->pi_connect_error, g_free); pi_render(a);
        set_status(a, "Legacy mode explicitly selected · Pi tools unavailable");
    } else if (!g_strcmp0(type, "connected")) {
        g_clear_pointer(&a->pi_connect_error, g_free);
        a->pi_connected = TRUE; pi_render(a);
        set_status(a, "Pi owner connected · fresh human consent required for tools");
    }
    else if (!g_strcmp0(type, "status")) {
        a->pi_parent_only = pi_parent_only_ready(jmember(packet, "result"));
        a->pi_normal_only = pi_normal_only_ready(jmember(packet, "result"));
        g_free(a->pi_state); a->pi_state = g_strdup(pi_observed_state(jmember(packet, "result")));
        pi_render(a);
    } else if (!g_strcmp0(type, "host_event")) {
        JsonNode *event = jmember(packet, "event");
        if (!g_strcmp0(jstr(jmember(event, "type")), "consent")) pi_consent(a, event);
        /* Routing recommendation never grants approval or triggers controls. */
    } else if (!g_strcmp0(type, "consent_closed")) {
        if (!g_strcmp0(a->pi_consent_id, jstr(jmember(packet, "answer_id")))) pi_close_dialog(a);
    } else if (!g_strcmp0(type, "event") && a->pi_chat && a->busy) {
        JsonNode *event = jmember(packet, "event");
        const char *kind = jstr(jmember(event, "type"));
        const char *text = jstr(jmember(event, "text"));
        if (!g_strcmp0(kind, "delta") && text) {
            render_delta(a, gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript)), text,
                !g_strcmp0(jstr(jmember(event, "channel")), "reasoning"));
            transcript_scroll_to_bottom(a);
        } else if (!g_strcmp0(kind, "turn_end")) {
            const char *stop = jstr(jmember(event, "stopReason"));
            if (!g_strcmp0(stop, "error") || !g_strcmp0(stop, "aborted")) a->pi_native_error = TRUE;
        } else if (!g_strcmp0(kind, "tool_execution_start") || !g_strcmp0(kind, "tool_execution_end")) {
            const char *tool = jstr(jmember(event, "tool"));
            JsonNode *err = jmember(event, "isError");
            char *status = g_strdup_printf("Pi tool %.80s · %s%s", tool ? tool : "unknown", kind,
                jboolean(err) && json_node_get_boolean(err) ? " · FAILED" : "");
            set_status(a, status); transcript_append(a, "Pi tool", status); g_free(status);
        }
    } else if (!g_strcmp0(type, "result") || !g_strcmp0(type, "error")) {
        gboolean ok = !strcmp(type, "result");
        if (!g_strcmp0(op, "chat")) {
            JsonNode *result = jmember(packet, "result");
            JsonNode *settled = jmember(result, "settled");
            if (ok && pi_cancelled_result(result)) {
                pi_finish_cancelled(a);
            } else pi_finish_chat(a, ok && jboolean(settled) && json_node_get_boolean(settled),
                ok ? NULL : "Pi request failed/interrupted; review native session. No retry.");
        } else if (!g_strcmp0(op, "on") || !g_strcmp0(op, "off")) {
            if (!strcmp(op, "on")) a->pi_on_pending = FALSE;
            else a->pi_off_pending = FALSE;
            a->pi_transition = a->pi_on_pending || a->pi_off_pending;
            if (!ok) { g_free(a->pi_state); a->pi_state = g_strdup("failed"); }
            pi_render(a);
        }
        if (!ok && !g_strcmp0(op, "connect")) {
            const char *error = jstr(jmember(packet, "error"));
            g_free(a->pi_connect_error);
            a->pi_connect_error = g_strdup(error && g_utf8_strlen(error, -1) <= 300 ? error :
                "Pi connection refused · no tools available · review owner/checkpoint; no retry");
            pi_route_update(a); set_status(a, a->pi_connect_error);
        } else if (!ok) set_status(a, "Pi request failed · review owner/checkpoint · no retry");
    } else if (!g_strcmp0(type, "notice")) {
        set_status(a, "Pi consent denied: action details exceeded display bound");
    } else if (!g_strcmp0(type, "unavailable")) pi_owner_unavailable(a);
}

static void pi_read_next(App *a);
static void pi_read(GObject *object, GAsyncResult *result, gpointer data) {
    App *a = data;
    gssize n = g_input_stream_read_finish(G_INPUT_STREAM(object), result, NULL);
    if (n <= 0) { if (!a->pi_dead)pi_diagnostic_fail(a,"bridge-eof"); return; }
    for (gssize i=0; i<n; i++) {
        char c = a->pi_buffer[i];
        if (c == '\n') {
            JsonParser *p = json_parser_new();
            gboolean valid = json_parser_load_from_data(p, a->pi_frame->str, a->pi_frame->len, NULL) &&
                JSON_NODE_HOLDS_OBJECT(json_parser_get_root(p));
            if (valid) pi_packet(a, json_parser_get_root(p));
            g_object_unref(p); g_string_truncate(a->pi_frame, 0);
            if (!valid) { pi_unavailable(a); return; }
            if (a->pi_dead) return;
        } else {
            if (!c || a->pi_frame->len >= PI_FRAME_MAX - 1) { pi_unavailable(a); return; }
            g_string_append_c(a->pi_frame, c);
        }
    }
    pi_read_next(a);
}
static void pi_read_next(App *a) {
    g_input_stream_read_async(a->pi_in, a->pi_buffer, sizeof a->pi_buffer,
        G_PRIORITY_DEFAULT, a->pi_io, pi_read, a);
}
/* Fixed launch/handoff only. Peer credentials describe establishment;
 * fd3 is intentionally inherited. This is NOT FD-transfer/code attestation. */
static char *pi_start_ticks(guint pid) {
    char *path = g_strdup_printf("/proc/%u/stat", pid), *text = NULL, *result = NULL;
    if (g_file_get_contents(path, &text, NULL, NULL)) {
        char *end = strrchr(text, ')');
        if (end && end[1] == ' ') {
            char **fields = g_strsplit(end + 2, " ", -1);
            if (g_strv_length(fields) > 19) result = g_strdup(fields[19]);
            g_strfreev(fields);
        }
    }
    g_free(path); g_free(text); return result;
}
static guint pi_sidecar_main_pid(void) {
    guint pid = 0;
    GDBusConnection *bus = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, NULL);
    if (!bus) return 0;
    GVariant *unit = g_dbus_connection_call_sync(bus, "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager", "GetUnit", g_variant_new("(s)", "hyprneuro.service"),
        G_VARIANT_TYPE("(o)"), G_DBUS_CALL_FLAGS_NONE, 1000, NULL, NULL);
    if (unit) {
        const char *path; g_variant_get(unit, "(&o)", &path);
        GVariant *state = g_dbus_connection_call_sync(bus, "org.freedesktop.systemd1", path,
            "org.freedesktop.DBus.Properties", "GetAll", g_variant_new("(s)", "org.freedesktop.systemd1.Unit"),
            G_VARIANT_TYPE("(a{sv})"), G_DBUS_CALL_FLAGS_NONE, 1000, NULL, NULL);
        gboolean live = FALSE;
        if (state) {
            GVariant *properties; const char *active = NULL, *substate = NULL, *job_path = NULL; guint job = 1;
            g_variant_get(state, "(@a{sv})", &properties);
            live = g_variant_lookup(properties, "ActiveState", "&s", &active) && !g_strcmp0(active, "active") &&
                g_variant_lookup(properties, "SubState", "&s", &substate) && !g_strcmp0(substate, "running") &&
                g_variant_lookup(properties, "Job", "(u&o)", &job, &job_path) && job == 0;
            g_variant_unref(properties); g_variant_unref(state);
        }
        if (!live) { g_variant_unref(unit); g_object_unref(bus); return 0; }
        GVariant *reply = g_dbus_connection_call_sync(bus, "org.freedesktop.systemd1", path,
            "org.freedesktop.DBus.Properties", "Get", g_variant_new("(ss)", "org.freedesktop.systemd1.Service", "MainPID"),
            G_VARIANT_TYPE("(v)"), G_DBUS_CALL_FLAGS_NONE, 1000, NULL, NULL);
        if (reply) {
            GVariant *value; g_variant_get(reply, "(v)", &value);
            if (g_variant_is_of_type(value, G_VARIANT_TYPE_UINT32)) pid = g_variant_get_uint32(value);
            g_variant_unref(value); g_variant_unref(reply);
        }
        g_variant_unref(unit);
    }
    g_object_unref(bus); return pid;
}
/* Diagnostics classify ONLY failure. No diagnostic frame can become a challenge. */
static const char *pi_broker_reject_stage(const char *stage) {
    const char *known[]={"peer","peer-uid","ui-identity","unit-command","unit-metadata","unit-state","unit-job","unit-pid","ui-process","ui-peer-pid","ui-uid","ui-cgroup","ui-exe-hash","launch-frame","child-identity","launch-ready","private-operation","unknown" ,NULL};
    const char *mapped[]={"broker-peer-check","broker-peer-uid","broker-ui-identity","broker-unit-command","broker-unit-metadata","broker-unit-state","broker-unit-job","broker-unit-pid","broker-ui-process","broker-ui-peer-pid","broker-ui-uid","broker-ui-cgroup","broker-ui-exe-hash","broker-launch-frame","broker-child-identity","broker-launch-ready","broker-private-operation","broker-unknown" ,NULL};
    for (int i=0;known[i];i++)if (!g_strcmp0(stage,known[i]))return mapped[i];
    return "broker-unknown";
}
static JsonNode *pi_broker_challenge(GSocket *socket,const char **stage,const char **category) {
    char frame[4097]; gsize length = 0;
    gint64 deadline = g_get_monotonic_time() + 3000000;
    *stage="challenge";*category="io";
    while (length < sizeof frame - 1) {
        gint64 left = deadline - g_get_monotonic_time();
        if (left <= 0) { *category="timeout";return NULL; }
        GError *error=NULL;
        if (!g_socket_condition_timed_wait(socket,G_IO_IN,left,NULL,&error)) {
            if (g_error_matches(error,G_IO_ERROR,G_IO_ERROR_TIMED_OUT))*category="timeout";
            g_clear_error(&error);return NULL;
        }
        gssize n = g_socket_receive(socket,frame+length,1,NULL,NULL);
        if (n==0) { *category=length?"framing":"eof";return NULL; }
        if (n!=1)return NULL;
        if (frame[length++] == '\n') {
            JsonParser *parser=json_parser_new();JsonNode *result=NULL;
            *category="json";
            if (json_parser_load_from_data(parser,frame,length,NULL)) {
                JsonNode *root=json_parser_get_root(parser);*category="schema";
                if (JSON_NODE_HOLDS_OBJECT(root)) {
                    JsonNode *reject=jmember(root,"error");
                    if (reject) {
                        /* Exact static envelope; no raw message, key, path or nonce projection. */
                        if (json_object_get_size(json_node_get_object(root))==1 && JSON_NODE_HOLDS_OBJECT(reject) &&
                            json_object_get_size(json_node_get_object(reject))==3 &&
                            !g_strcmp0(jstr(jmember(reject,"diagnostic")),"NONAUTHORITATIVE")) {
                            *stage=pi_broker_reject_stage(jstr(jmember(reject,"stage")));
                            const char *c=jstr(jmember(reject,"category"));
                            if (!strcmp(*stage,"broker-unknown") || (g_strcmp0(c,"timeout") && g_strcmp0(c,"identity") && g_strcmp0(c,"failure"))) {
                                *stage="broker-unknown";*category="unknown";
                            } else *category=pi_diagnostic_category(c);
                        }
                    } else {
                        const char *nonce=jstr(jmember(root,"nonce"));
                        gboolean valid=!g_strcmp0(jstr(jmember(root,"type")),"launch_challenge") && nonce && strlen(nonce)==64;
                        if (valid)for(const char *p=nonce;*p;p++)if(!g_ascii_isxdigit(*p)||g_ascii_isupper(*p))valid=FALSE;
                        if (valid)result=json_node_copy(root);
                    }
                }
            }
            g_object_unref(parser);return result;
        }
    }
    *category="framing";return NULL;
}
static gboolean pi_broker_attest(GSocket *socket, const char *packet) {
    gsize length = strlen(packet), sent = 0;
    gint64 deadline = g_get_monotonic_time() + 3000000;
    if (length > 4096) return FALSE;
    while (sent < length) {
        gint64 left = deadline - g_get_monotonic_time();
        if (left <= 0 || !g_socket_condition_timed_wait(socket, G_IO_OUT, left, NULL, NULL)) return FALSE;
        gssize n = g_socket_send(socket, packet + sent, length - sent, NULL, NULL);
        if (n <= 0) return FALSE;
        sent += n;
    }
    return TRUE;
}
static GSubprocess *pi_fixed_bridge(const char **stage,const char **category,char **verified_start) {
    *verified_start=NULL;*category="failure";
    *stage="policy-read";
    const char *policy_path = g_getenv("HYPRNEURO_PI_TRUSTED_POLICY");
    const char *policy_sha = g_getenv("HYPRNEURO_PI_TRUSTED_POLICY_SHA256");
    const char *broker_path = g_getenv("HYPRNEURO_PI_BROKER_SOCKET");
    char *raw = NULL, *digest = NULL, *entry_raw = NULL;
    gsize length = 0, entry_length = 0;
    JsonParser *parser = NULL; JsonNode *challenge = NULL;
    GSocketClient *client = NULL; GSocketAddress *address = NULL;
    GSocketConnection *connection = NULL; GSubprocessLauncher *launcher = NULL;
    GSubprocess *process = NULL; GCredentials *peer = NULL;
    char *before = NULL, *after = NULL, *child_start = NULL, *packet = NULL;
    struct stat info;
    if (!policy_path || !policy_sha || !broker_path || !g_path_is_absolute(policy_path) ||
        !g_path_is_absolute(broker_path) || lstat(policy_path, &info) || !S_ISREG(info.st_mode) ||
        info.st_uid != geteuid() || info.st_nlink != 1 || (info.st_mode & 077) || info.st_size > 4096) goto done;
    if (!g_file_get_contents(policy_path, &raw, &length, NULL) || length > 4096) goto done;
    *stage="policy-hash";
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, (guchar *)raw, length);
    if (g_strcmp0(digest, policy_sha)) goto done;
    *stage="policy-schema";
    parser = json_parser_new();
    if (!json_parser_load_from_data(parser, raw, length, NULL)) goto done;
    JsonNode *root = json_parser_get_root(parser);
    const char *python = jstr(jmember(root, "python")), *entry = jstr(jmember(root, "entry"));
    if (g_strcmp0(jstr(jmember(root,"schema")),"hyprneuro.trusted-launch/1") ||
        !python || !entry || !g_path_is_absolute(python) || !g_path_is_absolute(entry))goto done;
    *stage="entry-read";
    if (!g_file_get_contents(entry,&entry_raw,&entry_length,NULL) || entry_length>16384)goto done;
    g_clear_pointer(&digest, g_free);
    *stage="entry-hash";
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, (guchar *)entry_raw, entry_length);
    if (g_strcmp0(digest, jstr(jmember(root, "entry_sha256")))) goto done;
    *stage="broker-connect";
    client = g_socket_client_new(); g_socket_client_set_timeout(client, 3);
    address = g_unix_socket_address_new(broker_path);
    connection = g_socket_client_connect(client, G_SOCKET_CONNECTABLE(address), NULL, NULL);
    if (!connection) goto done;
    GSocket *socket = g_socket_connection_get_socket(connection);
    *stage="broker-peer";
    peer = g_socket_get_credentials(socket, NULL);
    if (!peer || g_credentials_get_unix_user(peer, NULL) != geteuid()) goto done;
    *stage="sidecar-identity";
    gint peer_pid = g_credentials_get_unix_pid(peer, NULL);
    if (peer_pid <= 0 || !(before = pi_start_ticks(peer_pid)) || pi_sidecar_main_pid() != (guint)peer_pid ||
        !(after = pi_start_ticks(peer_pid)) || g_strcmp0(before, after)) goto done;
    g_socket_set_blocking(socket, FALSE);
    *stage="challenge";
    challenge = pi_broker_challenge(socket,stage,category);
    if (!challenge)goto done;
    *category="failure";
    const char *nonce = jstr(jmember(challenge, "nonce"));
    if (g_strcmp0(jstr(jmember(challenge, "type")), "launch_challenge") || !nonce || strlen(nonce) != 64) goto done;
    for (const char *p = nonce; *p; p++) if (!g_ascii_isxdigit(*p) || g_ascii_isupper(*p)) goto done;
    *stage="spawn";
    launcher = g_subprocess_launcher_new(G_SUBPROCESS_FLAGS_STDIN_PIPE | G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                                         G_SUBPROCESS_FLAGS_STDERR_SILENCE);
    char *clean[] = { "PATH=/usr/bin:/bin", NULL };
    g_subprocess_launcher_set_environ(launcher, clean);
    const char *names[] = {"LANG", "LC_ALL", "HOME", "XDG_RUNTIME_DIR", "XDG_SESSION_ID", "DBUS_SESSION_BUS_ADDRESS",
                            "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", NULL};
    for (guint i = 0; names[i]; i++) if (g_getenv(names[i]))
        g_subprocess_launcher_setenv(launcher, names[i], g_getenv(names[i]), TRUE);
    int fd = dup(g_socket_get_fd(socket)); if (fd < 0) goto done;
    g_subprocess_launcher_take_fd(launcher, fd, 3); /* intended handoff, no other descriptor */
    process = g_subprocess_launcher_spawn(launcher, NULL, python, "-I", entry,
                                          "--explicit-connect", "--broker-fd=3", NULL);
    if (!process) goto done;
    *stage="child-start";
    const char *identifier = g_subprocess_get_identifier(process);
    char *end = NULL; guint64 child = identifier ? g_ascii_strtoull(identifier, &end, 10) : 0;
    if (!child || child > G_MAXINT || !end || *end || !(child_start = pi_start_ticks(child))) {
        g_clear_object(&process); goto done;
    }
    *stage="attest-write";
    packet = g_strdup_printf("{\"op\":\"launch\",\"nonce\":\"%s\",\"child_pid\":%u,\"child_start\":\"%s\"}\n",
                              nonce, (guint)child, child_start);
    if (!pi_broker_attest(socket, packet)) g_clear_object(&process);
    if (process)*verified_start=g_strdup(child_start);
done:
    /* Closing this duplicate leaves only the fixed child's fd3. Failure is EOF,
     * never a fallback launch or an automatic security decision. */
    g_clear_object(&connection); g_clear_object(&client); g_clear_object(&address);
    g_clear_object(&launcher); g_clear_object(&peer); g_clear_object(&parser);
    g_clear_pointer(&challenge, json_node_unref);
    g_free(raw); g_free(entry_raw); g_free(digest); g_free(before); g_free(after);
    g_free(child_start); g_free(packet); return process;
}
static void pi_start(App *a) {
    const char *stage=NULL,*category=NULL;
    char *verified_start=NULL;
    a->pi_process = pi_fixed_bridge(&stage,&category,&verified_start);
    if (!a->pi_process) { pi_diagnostic_fail_category(a,stage,category); return; }
    const char *identifier=g_subprocess_get_identifier(a->pi_process);
    guint64 pid=identifier?g_ascii_strtoull(identifier,NULL,10):0;
    char *start=pid && pid<=G_MAXUINT?pi_start_ticks(pid):NULL;
    if (start && verified_start && !strcmp(start,verified_start))g_subprocess_wait_async(a->pi_process,NULL,pi_owned_exit,verified_start);
    else {pi_diagnostic_emit("child-start","unknown",0);g_free(verified_start);}
    g_free(start);
    a->pi_in = g_subprocess_get_stdout_pipe(a->pi_process);
    a->pi_out = g_subprocess_get_stdin_pipe(a->pi_process);
    a->pi_io = g_cancellable_new(); a->pi_frame = g_string_new("");
    pi_read_next(a);
}
static void pi_stop(App *a) {
    if (a->pi_selecting && a->picker_cancel) g_cancellable_cancel(a->picker_cancel);
    pi_close_dialog(a);
    if (a->pi_io) g_cancellable_cancel(a->pi_io);
    if (a->pi_out) g_output_stream_close(a->pi_out, NULL, NULL);
    /* EOF is deliberate last-control disconnect cleanup, not a forced kill. */
}
/* Read-only operator metadata: never a connection/permission/control action. */
static char *pi_status_frame(App *a) {
    return g_strdup_printf("{\"mode\":\"%s\",\"connected\":%s,\"read_callable\":%s,\"fresh_consent_required\":true}\n",
        a->pi_optin ? "pi" : "legacy", a->pi_connected ? "true" : "false",
        a->pi_connected && a->pi_parent_only ? "true" : "false");
}
#include "pi-picker.inc"
static void pi_build(App *a) {
    a->pi_connect = gtk_button_new_with_label("Connect Pi owner…");
    gtk_widget_set_tooltip_text(a->pi_connect, "Explicitly select a prepared private parent-read owner. No permissions from settings; fresh human activation/read consent required.");
    g_signal_connect(a->pi_connect, "clicked", G_CALLBACK(pi_connect_clicked), a);
    gtk_widget_add_css_class(a->pi_connect, "hn-status-action");
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8); a->pi_row = row;
    a->pi_switch = GTK_SWITCH(gtk_switch_new());
    gtk_accessible_update_property(GTK_ACCESSIBLE(a->pi_switch), GTK_ACCESSIBLE_PROPERTY_LABEL, "MoE observed switch", -1);
    gtk_widget_set_tooltip_text(GTK_WIDGET(a->pi_switch), "Observed MoE state; each handoff needs fresh host consent");
    a->pi_label = gtk_label_new("MoE · unavailable");
    a->pi_cancel = gtk_button_new_with_label("Cancel Pi chat");
    gtk_widget_set_tooltip_text(a->pi_cancel, "Abort this chat connection and deny pending host consent; outcome may be unknown");
    GtkWidget *off = gtk_button_new_with_label("MoE off / cancel on");
    g_signal_connect(a->pi_switch, "state-set", G_CALLBACK(pi_switch_change), a);
    g_signal_connect(a->pi_cancel, "clicked", G_CALLBACK(pi_cancel_chat), a);
    g_signal_connect(off, "clicked", G_CALLBACK(pi_cancel_on), a);
    gtk_widget_set_sensitive(a->pi_cancel, FALSE);
    gtk_box_append(GTK_BOX(row), GTK_WIDGET(a->pi_switch));
    gtk_box_append(GTK_BOX(row), a->pi_label);
    gtk_box_append(GTK_BOX(row), off); gtk_box_append(GTK_BOX(row), a->pi_cancel);
    gtk_box_append(GTK_BOX(a->chat_page), row);
    gtk_widget_set_visible(row, a->pi_optin);
    a->pi_route = gtk_label_new(a->pi_optin ? "Text → Pi owner · attachments → legacy/tool-free (ordinary owner only)" : "Legacy sidecar · tool-free chat/media");
    gtk_accessible_update_property(GTK_ACCESSIBLE(a->pi_route),GTK_ACCESSIBLE_PROPERTY_DESCRIPTION,"hyprneuro-bootstrap-status",-1);
    gtk_label_set_wrap(GTK_LABEL(a->pi_route), TRUE);
    gtk_widget_add_css_class(a->pi_route, "dim-label");
    gtk_box_append(GTK_BOX(a->chat_page), a->pi_route);
    gtk_widget_set_visible(a->pi_route, TRUE);
    pi_render(a);
}
