// 登录页：被电脑网页上的「带参小程序码」扫进来，把 scene(票据) + wx.login 的 code
// 回传后端，后端换 openid 完成登录绑定。

const { API_BASE, TIMEOUT } = require('../../config.js')

Page({
  data: {
    status: 'loading', // loading | success | error
    title: '正在登录…',
    desc: '正在验证你的身份，请稍候',
    detail: '',
  },

  onLoad(options) {
    // 扫小程序码进入时，scene 在 options 里（URL 编码过一次）
    const scene = options && options.scene ? decodeURIComponent(options.scene) : ''

    if (!scene) {
      // 直接打开小程序（不是扫码进来的）时没有登录票据，无法登录。
      // 这里不再停在死胡同页面上，而是转到首页看完整说明，
      // 保证任何入口打开都能看到可用内容。
      wx.redirectTo({ url: '/pages/home/index' })
      return
    }

    this.ticket = scene
    this.doLogin()
  },

  doLogin() {
    this.setData({ status: 'loading', title: '正在登录…', desc: '正在验证你的身份，请稍候', detail: '' })

    wx.login({
      success: (res) => {
        if (!res.code) {
          this.fail('未能从微信获取登录凭证，请重试')
          return
        }
        this.bind(res.code)
      },
      fail: () => this.fail('调用微信登录失败，请检查网络后重试'),
    })
  },

  bind(code) {
    wx.request({
      url: `${API_BASE}/api/auth/wx/mp/bind`,
      method: 'POST',
      header: { 'content-type': 'application/json' },
      timeout: TIMEOUT,
      data: { state: this.ticket, code },
      success: (res) => {
        const body = res.data || {}
        if (res.statusCode === 200 && body.ok) {
          this.setData({
            status: 'success',
            title: '登录成功',
            desc: '可以回到电脑上继续操作了，这个页面可以关掉。',
            detail: body.nickname ? `已登录为「${body.nickname}」` : '',
          })
        } else {
          this.fail(body.detail || `登录失败（HTTP ${res.statusCode}）`)
        }
      },
      fail: (err) => {
        const msg = (err && err.errMsg) || ''
        // 域名没配好时最常见的报错，单独给一句人话提示
        if (msg.indexOf('domain') >= 0 || msg.indexOf('合法域名') >= 0) {
          this.fail('请求域名未在小程序后台配置为合法域名')
        } else {
          this.fail('网络请求失败，请检查网络后重试')
        }
      },
    })
  },

  fail(detail) {
    this.setData({
      status: 'error',
      title: '登录失败',
      desc: '请回到电脑上刷新二维码后重试',
      detail,
    })
  },

  retry() {
    if (this.ticket) {
      this.doLogin()
    } else {
      wx.exitMiniProgram && wx.exitMiniProgram()
    }
  },

  close() {
    wx.exitMiniProgram && wx.exitMiniProgram()
  },

  // 登录失败时给一条退路：回首页看使用说明
  goHome() {
    wx.redirectTo({ url: '/pages/home/index' })
  },
})
