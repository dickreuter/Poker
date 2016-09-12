import virtualbox
from PIL import Image
import time
from configobj import ConfigObj

class VirtualBoxController():
    def __init__(self):
        try:
            self.vbox = virtualbox.VirtualBox()
            config = ConfigObj("config.ini")
            mouse_control = config['control']
            if mouse_control!='Direct mouse control':
                self.vm = self.vbox.find_machine(mouse_control)
                self.session = self.vm.create_session()
        except Exception as e:
            print (e)

    def get_vbox_list(self):
        vm_list=[vm.name for vm in self.vbox.machines]
        return vm_list

    def get_screenshot_vbox(self):
        h, w, _, _, _, _= self.session.console.display.get_screen_resolution(0)
        png = self.session.console.display.take_screen_shot_to_array(0, h, w, virtualbox.library.BitmapFormat.png)
        open('screenshot_vbox.png', 'wb').write(png)
        #image=Image.fromarray(png)
        #image.show()
        time.sleep(0.5)
        return Image.open('screenshot_vbox.png')

    def mouse_move_vbox(self,x,y,dz=0,dw=0):
        self.session.console.mouse.put_mouse_event_absolute(x,y,dz,dw, 0)

    def mouse_click_vbox(self,x,y,dz=0,dw=0):
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0b1)
        time.sleep(0.2)
        self.session.console.mouse.put_mouse_event_absolute(x, y, dz, dw, 0)

if __name__=='__main__':
    vb=VirtualBoxController()
    vb.mouse_move_vbox(1,1)
    vb.mouse_click_vbox()
    vb.get_screenshot_vbox()
    vb.get_vbox_list()
