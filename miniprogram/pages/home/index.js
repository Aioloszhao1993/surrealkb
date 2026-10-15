const { ICP_NUMBER } = require('../../config.js')

Page({
  data: {
    icp: ICP_NUMBER || '',
  },

  onLoad(options) {
    // 从分享卡片或小程序码带 scene 进来时，交给登录页处理
    if (options && options.scene) {
      wx.redirectTo({
        url: `/pages/login/index?scene=${options.scene}`,
      })
    }
  },

  openPrivacy() {
    // 优先打开微信后台配置的官方隐私协议页；未配置时回退到本地页面
    if (wx.openPrivacyContract) {
      wx.openPrivacyContract({
        fail: () => {
          wx.navigateTo({ url: '/pages/privacy/index' })
        },
      })
      return
    }
    wx.navigateTo({ url: '/pages/privacy/index' })
  },

  openAgreement() {
    wx.navigateTo({ url: '/pages/agreement/index' })
  },
})
