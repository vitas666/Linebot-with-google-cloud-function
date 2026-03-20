QUESTION_MAP = {
    "39da25f3": "目前的家庭／扶養狀況為何？",
    "5be54049": "您目前主要接觸或投資的金融商品類型是？",
    "73e938fa": "您目前是否有負債或貸款？",
    "17e95034": "您的投資組合配置較接近下列何者？",
    "308f6275": "您目前是否有明確的財務或人生目標？",
    "60483d20": "您的投資經驗大約多久？",
    "35a2cdf3": "您目前最大的固定支出項目是？",
    "113225a5": "您目前的年齡是？",
    "566fef82": "當投資出現波動時，您通常會怎麼做？",
}

ANSWER_MAP = {
    "39da25f3": {  # 家庭／扶養狀況
        "單身/沒有扶養義務": {
            "dependents": 0,
            "family_status": "single"
        },
    },
    "5be54049": {  # 投資商品類型
        "股票/ETF/期貨/虛擬貨幣/金融商品": {
            "asset_types": ["stock", "etf", "futures", "crypto"],
            "experience_level": "intermediate"
        }
    },
    "73e938fa": {  # 負債狀況
        "沒有": {
            "has_debt": False,
            "debt_level": "none"
        }
    },
    "17e95034": {  # 投資組合配置
        "個股佔比大於ETF": {
            "portfolio_style": "stock_heavy",
            "risk_level": "high"
        }
    },
    "308f6275": {  # 財務／人生目標
        "暫時沒有": {
            "has_goal": False,
            "goal_clarity": "low"
        }
    },
    "60483d20": {  # 投資經驗
        "一年以上": {
            "investment_years_min": 1,
            "experience_level": "intermediate"
        }
    },
    "35a2cdf3": {  # 固定支出
        "房租": {
            "expense_type": "rent",
            "expense_fixed": True
        }
    },
    "113225a5": {  # 年齡
        "30": {
            "age": 30,
            "age_group": "30s"
        }
    },
    "566fef82": {  # 投資行為
        "部分賣出，考慮低點加碼": {
            "behavior_type": "semi_active",
            "panic_sell": False,
            "dip_buying": True
        }
    }
}