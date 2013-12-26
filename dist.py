from math import *

class Point(object):
    
    lat = None
    lng = None
    alt = None
    extra = None
    
    def __init__(self, lat=None, lng=None, alt=None):
        self.lat = lat
        self.lng = lng
        self.alt = alt

    def __repr__(self):
        return "{}".format(self.extra)
    
    def equals(self, other):
        return self.lat == other.lat and self.lng == other.lng and self.alt == other.alt

    def __div__(self, alpha):
        self.lat, self.lng, self.alt = map(lambda x: x / alpha, [self.lat, self.lng, self.alt])
        return self
    
class VincentyDistance(object):

    def __init__(self):
        self.a = 6378137.0
        self.f = 1 / 298.257223563

    def distance(self, src, dst):
        dstlat = radians(dst.lat)
        dstlng = radians(dst.lng)
        srclat = radians(src.lat)
        srclng = radians(src.lng)
        b = (1 - self.f) * self.a
        U1 = atan((1 - self.f) * tan(srclat))
        U2 = atan((1 - self.f) * tan(dstlat))
        L = dstlng - srclng

        alpha1 = alpha2 = s = 0.0

        lambda_lng = L
        for i in range(4):
            sin_sigma = sqrt((cos(U2) * sin(lambda_lng)) ** 2 + (cos(U1) * sin(U2) - sin(U1) * cos(U2) * cos(lambda_lng)) ** 2)
            if sin_sigma == 0:
                return 0
            cos_sigma = sin(U1) * sin(U2) + cos(U1) * cos(U2) * cos(lambda_lng)
            sigma = atan(sin_sigma / cos_sigma)

            sin_alpha = cos(U1) * cos(U2) * sin(lambda_lng) / sin_sigma
            cos_sqr_alpha = 1 - sin_alpha ** 2
            cos_sqr_sigma_m = cos_sigma - (2 * sin(U1) * sin(U2) / cos_sqr_alpha)

            C = (self.f / 16.) * cos_sqr_alpha * (4 + (self.f * (4 - (3 * cos_sqr_alpha))))
            lambda_lng = L + (
                (1 - C) * self.f * sin_alpha *
                (sigma + (C * sin_sigma * (cos_sqr_sigma_m +
                (C * cos_sigma * (-1 + (2 * cos_sqr_sigma_m ** 2))))
                )))
        u_sqr = cos_sqr_alpha * (self.a ** 2 - b ** 2) / b ** 2
        A = 1 + u_sqr / 16384. * (4096 + u_sqr * (-768 + u_sqr * (320 - 175 * u_sqr)))
        B = u_sqr / 1024. * (256 + u_sqr * (-128 + u_sqr * (74 - 47 * u_sqr)))
        delta_sigma = B * sin_sigma * (cos_sqr_sigma_m + B / 4. * (cos_sigma * (-1 + 2 * cos_sqr_sigma_m**2) - (B / 6. * cos_sqr_sigma_m * (-3 + 4 * sin_sigma **2) * (-3 + 4 * cos_sqr_sigma_m**2))))
        s = b * A * (sigma - delta_sigma)
        return s
