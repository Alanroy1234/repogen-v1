import webview
import threading
import time

class Api:
    def get_live_tags(self):
        return {1: {"value": 123}, "2": {"value": 456}}
        
def start_webview():
    api = Api()
    window = webview.create_window("Test", html="""
        <html><body>
        <script>
            window.addEventListener('pywebviewready', async () => {
                try {
                    const live = await pywebview.api.get_live_tags();
                    document.body.innerHTML += "<br>Result keys: " + Object.keys(live).join(", ");
                    document.body.innerHTML += "<br>Value 1: " + (live[1] ? live[1].value : 'missing');
                    document.body.innerHTML += "<br>Value 2: " + (live["2"] ? live["2"].value : 'missing');
                    console.log(live);
                } catch(e) {
                    document.body.innerHTML += "<br>Error: " + e;
                }
            });
        </script>
        </body></html>
    """, js_api=api)
    webview.start()

if __name__ == "__main__":
    t = threading.Thread(target=start_webview)
    t.start()
    time.sleep(3)
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)
