import sys

from kivy.clock import Clock
from kivy.core.window import Window

sgf, out, target = sys.argv[2], sys.argv[3], int(sys.argv[4])
sys.argv = sys.argv[:2]
import katrain.__main__ as km

orig = km.KaTrainApp.on_start


def on_start(self):
    orig(self)
    Window.size = (1600, 1000)

    def load(_dt):
        self.gui.load_sgf_file(sgf, fast=True)
        Clock.schedule_once(goto, 3)

    def goto(_dt):
        self.gui.game.redo(target)
        self.gui.update_state()
        Clock.schedule_once(shot, 6)

    def shot(_dt):
        Window.screenshot(name=out)
        Clock.schedule_once(lambda _dt: self.stop(), 1)

    Clock.schedule_once(load, 3)


km.KaTrainApp.on_start = on_start
km.run_app()
