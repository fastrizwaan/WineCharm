    def show_info_dialog(self, title, message, callback=None):
        """
        Show an information dialog with an optional callback when closed.
        Uses Adw.MessageDialog with non-deprecated constructor parameters.
        """
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            modal=True,
            heading=title,
            body=message,
            close_response="ok",    # Instead of set_close_response()
            default_response="ok"   # Instead of set_default_response()
        )
        
        dialog.add_response("ok", "OK")
        
        def on_response(d, r):
            d.close()
            if callback is not None:
                callback()
        
        dialog.connect("response", on_response)
        dialog.present()


