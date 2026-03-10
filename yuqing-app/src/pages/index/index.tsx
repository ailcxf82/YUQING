import React from 'react'
import { View } from '@tarojs/components'
import NewsKeyboardScreen from '../../components/NewsKeyboardScreen'
import './index.scss'

export default function Index() {
  return (
    <View className='page-index' style={{ minHeight: '100vh' }}>
      <NewsKeyboardScreen />
    </View>
  )
}
