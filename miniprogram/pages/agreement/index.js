const { CONTACT_EMAIL } = require('../../config.js')

Page({
  data: {
    email: CONTACT_EMAIL || '',
  },
})
