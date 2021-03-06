import React from "react";
import logo from "../../assets/images/logo.png";
import { Link } from "react-router-dom";

/**
 * Defines the Header of PrivacyMail
 */
const Header = () => {
    return (
        <div className="header">
            <Link to="/">
                <div>
                    <img src={logo} alt=""></img>
                    <h1>PrivacyMail</h1>
                </div>
            </Link>
        </div>
    );
};
export default Header;
