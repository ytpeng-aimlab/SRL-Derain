import chainer
import chainer.links as L
import chainer.functions as F
import chainerrl
from chainerrl.agents import a3c
import torch.nn.functional as FT
import torch
import torch.nn as nn

class DilatedConvBlock(chainer.Chain):

    def __init__(self, d_factor, weight, bias):
        super(DilatedConvBlock, self).__init__(
            diconv=L.DilatedConvolution2D( in_channels=64, out_channels=64, ksize=3, stride=1, pad=d_factor, dilate=d_factor, nobias=False, initialW=weight, initial_bias=bias),
        )

        self.train = True

    def __call__(self, x):
        h = F.relu(self.diconv(x))
        return h


class MyFcn(chainer.Chain, a3c.A3CModel):
 
    def __init__(self, n_actions):
        w = chainer.initializers.HeNormal()
        super(MyFcn, self).__init__(
            # shared model
            conv1=L.Convolution2D(3, 64, 3, stride=1, pad=1, nobias=False, initialW=w, initial_bias=None),
            diconv2=DilatedConvBlock(2, w, None),
            diconv3=DilatedConvBlock(3, w, None),
            diconv4=DilatedConvBlock(4, w, None),
            # policy net
            diconv5_pi=DilatedConvBlock(3, w, None),
            diconv6_pi=DilatedConvBlock(2, w, None),
            conv7_Wz=L.Convolution2D( 64, 64, 3, stride=1, pad=1, nobias=True, initialW=w),
            conv7_Uz=L.Convolution2D( 64, 64, 3, stride=1, pad=1, nobias=True, initialW=w),
            conv7_Wr=L.Convolution2D( 64, 64, 3, stride=1, pad=1, nobias=True, initialW=w),
            conv7_Ur=L.Convolution2D( 64, 64, 3, stride=1, pad=1, nobias=True, initialW=w),
            conv7_W=L.Convolution2D( 64, 64, 3, stride=1, pad=1, nobias=True, initialW=w),
            conv7_U=L.Convolution2D( 64, 64, 3, stride=1, pad=1, nobias=True, initialW=w),
            conv8_pi=chainerrl.policies.SoftmaxPolicy(L.Convolution2D( 64, n_actions, 3, stride=1, pad=1, nobias=False, initialW=w, initial_bias=None)),
            # value net
            diconv5_V=DilatedConvBlock(3, w, None),
            diconv6_V=DilatedConvBlock(2, w, None),
            conv7_V=L.Convolution2D( 64, 1, 3, stride=1, pad=1, nobias=False, initialW=w, initial_bias=None),
        )
        self.train = True
 
    def pi_and_v(self, x):
        # shared model 
        h = F.relu(self.conv1(x[:,0:3,:,:]))
        h = self.diconv2(h)
        h = self.diconv3(h)
        h = self.diconv4(h)
        # policy net
        h_pi = self.diconv5_pi(h)
        x_t = self.diconv6_pi(h_pi)
        h_t1 = x[:,-64:,:,:]
        z_t = F.sigmoid(self.conv7_Wz(x_t)+self.conv7_Uz(h_t1))
        r_t = F.sigmoid(self.conv7_Wr(x_t)+self.conv7_Ur(h_t1))
        h_tilde_t = F.tanh(self.conv7_W(x_t)+self.conv7_U(r_t*h_t1))
        h_t = (1-z_t)*h_t1+z_t*h_tilde_t
        pout = self.conv8_pi(h_t)
        # value net
        h_V = self.diconv5_V(h)
        h_V = self.diconv6_V(h_V)
        vout = self.conv7_V(h_V)
       
        return pout, vout, h_t
    
class Reward_Predictor(nn.Module):
    def __init__(self, image_size):
        super(Reward_Predictor, self).__init__()
        img_h, img_w = image_size
        input_dim = 6
        self.conv1 = nn.Conv2d(input_dim, 64, 3, stride=1, padding=(1, 1), bias=True)
        self.diconv2 = nn.Conv2d(64, 64, 3, stride=1, padding=(2, 2), dilation=2, bias=True)
        self.diconv3 = nn.Conv2d(64, 64, 3, stride=1, padding=(3, 3), dilation=3, bias=True)
        self.diconv4 = nn.Conv2d(64, 64, 3, stride=1, padding=(2, 2), dilation=2, bias=True)
        self.conv5 = nn.Conv2d(64, 1, 3, stride=1, padding=(1, 1), bias=True)
        self.fc1 = nn.Linear(1*img_h*img_w, 128)
        self.fc2 = nn.Linear(128, 1)
        
    def forward(self, x):
        B, C, H, W = x.shape
        x = FT.relu(self.conv1(x))
        x = FT.relu(self.diconv2(x))
        x = FT.relu(self.diconv3(x))
        x = FT.relu(self.diconv4(x))
        x = self.conv5(x)
        x = x.view(B, -1) #[B, 1*H*W]
        x = self.fc1(x)
        x = torch.tanh(self.fc2(x))
        return x