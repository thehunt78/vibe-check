import cv2
import numpy as np
from numba import njit

@njit
def align_down(size, align):
    return (size & ~((align)-1))

@njit
def align_up(size, align):
    return align_down(size + align - 1, align)

@njit
def remove_padding_and_unpack_fast(data, width, height, bit_width, out):
    """Remove padding and rearrange packed 16-bit values into unpacked."""
    real_width = width // 8 * bit_width
    align_width = align_up(real_width, 32)
    jj = 0
    k = 0
    for y in range(height):
        j = jj
        for x in range(width//4):
            low = data[j+4]
            out[k] = (data[j] << 2) + ((low) & 0x3)
            out[k+1] = (data[j+1] << 2) + ((low >> 2) & 0x3)
            out[k+2] = (data[j+2] << 2) + ((low >> 4) & 0x3)
            out[k+3] = (data[j+3] << 2) + ((low >> 6) & 0x3)
            j += 5
            k += 4
        jj += align_width
        
def curves_to_lut(curves, in_range=1024, gamma=2.2):
    """Build a LUT for a given set of curves, similar but not equal to Photoshop curves."""
    lut = []
    x_values = np.arange(in_range).astype(float)
    for curve in curves:
        curve = np.asarray(curve).astype(float)
        ys, xs = curve.T / 256
        z = np.polyfit(xs, ys, len(xs)-1)
        f = np.poly1d(z)
        out = f(x_values / in_range)
        out = np.maximum(out, 0)
        out **= 1/gamma
        out *= 256
        out = np.minimum(out, 255)
        lut.append(out)
    return np.asarray(lut).astype(np.uint8)

@njit
def apply_lut(img16, img8, lut):
    h,w = img16.shape[:2]
    n = h * w
    img16_flat = img16.reshape(-1,3)
    img8_flat = img8.reshape(-1,3)
    for i in range(n):
        for j in range(3):
            img8_flat[i][j] = lut[j][img16_flat[i][j]]
        
@njit
def remove_padding_and_unpack_quarter_bgr_preview(data, width, height, bit_width, out):
    """Same as above, but at quarter resolution unpacked directly to BGR."""
    real_width = width // 8 * bit_width
    align_width = align_up(real_width, 32)
    skip_length = align_width * 4
    jj = 0
    k = 0
    n = width//4
    for y in range(height//4):
        j = jj
        for x in range(width//4):
            out[k+0] = data[j]
            out[k+1] = data[j+1]
            out[k+2] = data[j+align_width+1]
            j += 5
            k += 3
        jj += skip_length

@njit
def zebra(img, width, height):
    i = 0
    n = width * height * 3
    for y in range(height):
        for x in range(width//3):
            if img[i] == 255:
                img[i] = 0
            if img[i+1] == 255:
                img[i+1] = 0
            if img[i+2] == 255:
                img[i+2] = 0          
            i += 9
        i += 3
        if i > n:
            break

class RawProcessor:
    """For 16-bit output leave curves=None."""
    def __init__(self, width, height, curves=None, mode='bgr'):
        self.w = width
        self.h = height
        self.img16_bayer = np.zeros((height*width), np.uint16)
        self.img16 = np.zeros((height,width,3), np.uint16)
        self.lut = None
        if curves is not None:
            self.lut = curves_to_lut(curves, in_range=1024)
            self.img8_lut = np.zeros((height,width,3), np.uint8)
        self.mode = cv2.COLOR_BAYER_RG2BGR if mode == 'bgr' else cv2.COLOR_BAYER_RG2RGB
        
    def __call__(self, data):
        remove_padding_and_unpack_fast(data, self.w, self.h, 10, self.img16_bayer)
        cv2.cvtColor(self.img16_bayer.reshape(self.h, self.w), self.mode, self.img16)
        if self.lut is None:
            return self.img16
        apply_lut(self.img16, self.img8_lut, self.lut)
        return self.img8_lut