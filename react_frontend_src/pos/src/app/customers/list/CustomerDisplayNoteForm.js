import React, { Component } from "react"
import { intlShape } from "react-intl"
import PropTypes from "prop-types"
import validator from 'validator'
import { v4 } from "uuid"
import Inputmask from "inputmask"
// import Inputmask from "inputmask/dist/inputmask/inputmask.date.extensions";

import CustomerFormError from "./CustomerFormError"


class CustomerDisplayNoteForm extends Component {
    constructor(props) {
        super(props)
        console.log(props)
        this.textarea = React.createRef()
    }

    PropTypes = {
        intl: intlShape.isRequired,
    }

    render() {
        const create = this.props.create
        const update = this.props.update
        const title = this.props.title
        const error_data = this.props.errorData
        const onSubmit = this.props.onSubmit
        const onCancel = this.props.onClickCancel
        const selected_noteID = this.props.selectedNoteID
        let defaultValue = ""
        let acknowledged = false

        if (create) {
            defaultValue = ""
            this.textarea.current.value = defaultValue
        }

        // set initial value on update
        if (update) {
            const notes = this.props.notes.data
            var i           
            for (i = 0; i < notes.length; i++) {
                if (notes[i].id === selected_noteID) {
                    defaultValue = notes[i].Note
                    acknowledged = notes[i].Acknowledged
                }
            }       
        }        

        return (
            <div>
                {(update) ? 
                    <span className="pull-right">
                    { (acknowledged) ? 
                        <span className="text-green"> 
                            <i className="fa fa-check"></i> {' '}
                            Acknowledged
                        </span>:
                        <span>
                            To be processed
                        </span>
                    }
                    { ' ' + ' ' }
                    <button
                        className='btn btn-xs btn-default'
                        onClick={f=>f}
                    >
                        <i className="fa fa-refresh"></i> {' '} Change note status
                    </button>
                    </span>
                    : ""}
                <label htmlFor="CustomersNoteTextarea">{title}</label>
                <form onSubmit={onSubmit}>
                    <textarea
                        ref={this.textarea}
                        id="CustomersNoteTextarea" 
                        className="form-control"
                        defaultValue={defaultValue}
                        name="Note" 
                    />
                    <CustomerFormError message={ (error_data.Note) ? error_data.Note : "" } /> 
                    <br />
                    <button className="btn btn-primary pull-right">Save</button>
                </form>
                <button className="btn btn-link" onClick={onCancel.bind(this)}>Cancel</button>
            </div>
        )
    }
}

export default CustomerDisplayNoteForm

