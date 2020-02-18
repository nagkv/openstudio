import React, { Component } from "react"
import { intlShape } from "react-intl"
import PropTypes from "prop-types"
import { v4 } from "uuid"

import Currency from "../../../components/ui/Currency"
import PaymentMethodName from "../components/PaymentMethodNameContainer"
import ValidationListItems from "./ValidationListItems"


class ValidationList extends Component {
    constructor(props) {
        super(props)
        console.log(props)
    }

    PropTypes = {
        intl: intlShape.isRequired,
        setPageTitle: PropTypes.function,
        app: PropTypes.object,
        data: PropTypes.object
    }

    render() {
        const app = this.props.app
        const data = this.props.data

        console.log("app.cart_validation_data.receipt_payment_methods_id")
        console.log(app.cart_validation_data.receipt_payment_methods_id)

        return (
            !(app.loaded) || !(app.cart_validated) ? 
                "Loading" :
            <div>
                Payment Method: <PaymentMethodName 
                                    methods={app.payment_methods}
                                    payment_method_id={app.cart_validation_data.receipt_payment_methods_id}/> <br /><br />
                <ValidationListItems items={app.cart_validation_data.receipt_items}
                                     total={app.cart_validation_data.receipt_amounts.TotalPriceVAT} />

            </div>
        )
    }
}

export default ValidationList
