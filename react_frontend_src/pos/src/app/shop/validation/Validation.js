import React, { Component } from "react"
import { intlShape } from "react-intl"
import PropTypes from "prop-types"
import { v4 } from "uuid"
import { toast } from 'react-toastify'

import PageTemplate from "../../../components/PageTemplate"
import Box from "../../../components/ui/Box"
import BoxBody from "../../../components/ui/BoxBody"
import BoxHeader from "../../../components/ui/BoxHeader"

import ButtonNextOrder from "./ButtonNextOrder"
import ValidationList from "./ValidationList"


class Validation extends Component {
    constructor(props) {
        super(props)
        console.log(props)
    }

    PropTypes = {
        intl: intlShape.isRequired,
        setPageTitle: PropTypes.function,
        state: PropTypes.object,
        app: PropTypes.object,
        selected_method: PropTypes.int,
        clearSelectedPaymentMethod: PropTypes.function,
        clearCartItems: PropTypes.function,
        clearSelectedCustomer: PropTypes.function
    }

    componentWillMount() {
        this.props.setPageTitle(
            this.props.intl.formatMessage({ id: 'app.pos.shop.validation.page_title' })
        )
        this.props.validateCart(this.props.state)
    }


    onClickNextOrder() {
        console.log('next order clicked')

        // DO THIS IN APP/DUCK/OPERATIONS (It's a better place :) )

        // const cartItems = this.props.cart.items
        // let cartHasClasscard = false
        // let cartHasMembership = false
        // let cartHasSubscription = false
        // let cartHasClassReconcileLater = false
        // var i
        // for (i = 0; i < cartItems.length; i++) {
        //     console.log(cartItems[i])
        //     switch (cartItems[i].item_type) {
        //         case "classcard":
        //             cartHasClasscard = true
        //             break
        //         case "subscription":
        //             cartHasSubscription = true
        //             break
        //         case "membership":
        //             cartHasMembership = true
        //             break
        //         case "class_reconcile_later":
        //             cartHasClassReconcileLater = true
        //     }
        // } 

        // if ( (cartHasClasscard) || (cartHasSubscription) || (cartHasMembership) || (cartHasClassReconcileLater) ){
        //     this.props.fetchCustomersSchoolInfo(this.props.selected_customerID)
        // }
        // // if (cartHasSubscription) {
        // //     this.props.fetchCustomersSubscriptions()
        // // }
        // // if (cartHasSubscription) {
        // //     this.props.fetchCustomersMemberships()
        // //     this.props.fetchCustomersMembershipsToday()
        // // }

        // this.props.clearSelectedPaymentMethod()
        // this.props.clearCartItems()
        // this.props.clearSelectedCustomer()
        
        this.props.history.push('/shop/products')
    }
    
    render() {
        const app = this.props.app
        console.log('app')
        console.log(app)
        const history = this.props.history

        return (
            <PageTemplate app_state={app}>
                {(app.cart_validating) ?
                    <div className="row">
                        <div className="col-md-4 col-md-offset-4">
                            <Box>
                                <BoxBody className="center">
                                    <div className='text-muted'>
                                        <i className="fa fa-spinner fa-pulse fa-5x fa-fw"></i>
                                    </div>
                                    <br /><br />
                                    <span className="bold">Validating cart...</span><br /><br />
                                    Please wait... 
                                </BoxBody>
                            </Box>
                        </div>
                    </div>
                    : (app.cart_validation_error) ?
                        <div>
                            <div className="row">
                                <div className="col-md-12">
                                    <ButtonNextOrder onClick={this.onClickNextOrder.bind(this)} />
                                </div>
                            </div>
                            <div className="row">
                                <div className="col-md-4 col-md-offset-4">
                                    <Box>
                                        <BoxBody className="center">
                                            <div className="text-orange">
                                                <i className="fa fa-exclamation-triangle fa-5x"></i>
                                            </div>
                                            <br /><br />
                                            Hmm... I seem to have found something that needs your attention while validating this shopping cart. <br /><br />
                                            <div className="text-orange bold">
                                                {app.cart_validation_data.message}
                                            </div>
                                        </BoxBody>
                                    </Box>
                                </div>
                            </div>
                        </div> :
                        // Everything ok
                        <div>
                            <div className="row">
                                <div className="col-md-12">
                                    <ButtonNextOrder onClick={this.onClickNextOrder.bind(this)} />
                                </div>
                            </div>
                            <div className="row">
                                <div className="col-md-4 col-md-offset-4">
                                    <Box>
                                        <BoxBody>
                                            <div className='text-green center'>
                                                <i className="fa fa-check fa-5x"></i>
                                            </div>
                                            <br />
                                            <div className="center">
                                                <span className="bold text-green">SUCCESS!<br /><br /></span>
                                            </div>
                                            <ValidationList app={app}
                                                            data={app.cart_validation_data} />
                                            { (app.cart_validation_data.checkin_did) ?
                                                (app.cart_validation_data.checkin_status == "ok") ?
                                                    <span className="text-green">
                                                        Customer checked in to class
                                                    </span> : 
                                                    <span className="text-red">
                                                        Class checkin failed <br />
                                                        {app.cart_validation_data.checkin_message}
                                                    </span>
                                                : ""
                                            }
                                            <hr />
                                            <a href={app.cart_validation_data.receipt_link} 
                                               target="_blank"
                                               className="btn btn-default pull-right">
                                                <i className="fa fa-print"></i> Print receipt
                                            </a>
                                            <span className="text-green">
                                                <i className="fa fa-leaf"></i> Please consider the environment before printing!
                                            </span><br /><br />
                                        </BoxBody>
                                    </Box>
                                </div>
                            </div>
                        </div>
                }
            </PageTemplate>
        )
    }
}

export default Validation
